import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from my_agent_app.analysis.config import get_max_attempts, get_stale_timeout_minutes
from my_agent_app.analysis.dedup import prepare_analysis, recover_orphans
from my_agent_app.analysis.handler import AnalysisHandler
from my_agent_app.models import Report, ReportStatus

NOW = datetime.now(timezone.utc)
KW = dict(max_attempts=3, stale_minutes=30)


def event(uid: str, ts: datetime) -> dict:
    return {"uid": uid, "type": "Warning", "reason": "BackOff", "message": "m", "namespace": "default",
            "involved_object": {"kind": "Pod", "name": "p", "namespace": "default"}, "timestamp": ts.isoformat()}


async def add_report(sessionmaker, status, uids, *, updated_at=None, attempt_count=1) -> Report:
    updated_at = updated_at or NOW
    async with sessionmaker() as session, session.begin():
        report = Report(status=status, event_uids=uids, attempt_count=attempt_count,
                        created_at=updated_at, updated_at=updated_at)
        session.add(report)
    return report


async def all_reports(sessionmaker) -> list[Report]:
    async with sessionmaker() as session:
        return list((await session.execute(select(Report))).scalars())


async def test_event_without_report_is_analyzed_and_report_created(sessionmaker):
    result = await prepare_analysis(sessionmaker, [event("u1", NOW)], **KW)

    assert [e["uid"] for e in result.events] == ["u1"]
    [report] = await all_reports(sessionmaker)
    assert report.id == result.report_id
    assert report.status == ReportStatus.EM_ANALISE
    assert report.event_uids == ["u1"] and report.attempt_count == 1


@pytest.mark.parametrize("status", [
    ReportStatus.EM_ANALISE, ReportStatus.COMPLETO, ReportStatus.CORRIGINDO, ReportStatus.FALHA_CORRECAO])
async def test_active_report_ignores_event(sessionmaker, status):
    await add_report(sessionmaker, status, ["u1"])
    result = await prepare_analysis(sessionmaker, [event("u1", NOW + timedelta(hours=1))], **KW)
    assert result.events == [] and result.report_id is None
    assert len(await all_reports(sessionmaker)) == 1


async def test_corrigido_reanalyzed_only_on_recurrence(sessionmaker):
    fixed_at = NOW - timedelta(minutes=10)
    await add_report(sessionmaker, ReportStatus.CORRIGIDO, ["u1", "u2", "u3"], updated_at=fixed_at)

    result = await prepare_analysis(sessionmaker, [
        event("u1", fixed_at + timedelta(minutes=1)),   # reincidiu
        event("u2", fixed_at - timedelta(minutes=1)),   # ainda vivo, anterior a correcao
        event("u3", fixed_at),                          # igual: nao reanalisa
    ], **KW)

    assert [e["uid"] for e in result.events] == ["u1"]


async def test_active_and_old_corrigido_coexist_ignores(sessionmaker):
    await add_report(sessionmaker, ReportStatus.CORRIGIDO, ["u1"], updated_at=NOW - timedelta(hours=2))
    await add_report(sessionmaker, ReportStatus.EM_ANALISE, ["u1"])
    result = await prepare_analysis(sessionmaker, [event("u1", NOW + timedelta(minutes=5))], **KW)
    assert result.events == []


async def test_incomplete_reanalyzed_by_presence_and_increments_attempts(sessionmaker):
    await add_report(sessionmaker, ReportStatus.INCOMPLETO, ["u1"], attempt_count=1)
    result = await prepare_analysis(sessionmaker, [event("u1", NOW - timedelta(hours=1))], **KW)

    assert [e["uid"] for e in result.events] == ["u1"]
    new = next(r for r in await all_reports(sessionmaker) if r.id == result.report_id)
    assert new.attempt_count == 2


async def test_incomplete_stops_at_limit_and_warns(sessionmaker, caplog):
    await add_report(sessionmaker, ReportStatus.INCOMPLETO, ["u1"], attempt_count=3)
    with caplog.at_level(logging.WARNING):
        result = await prepare_analysis(sessionmaker, [event("u1", NOW)], **KW)
    assert result.events == []
    assert "u1" in caplog.text and "limite" in caplog.text


async def test_incomplete_limit_is_configurable(sessionmaker):
    await add_report(sessionmaker, ReportStatus.INCOMPLETO, ["u1"], attempt_count=3)
    result = await prepare_analysis(sessionmaker, [event("u1", NOW)], max_attempts=5, stale_minutes=30)
    assert [e["uid"] for e in result.events] == ["u1"]


async def test_newer_incomplete_wins_over_older_corrigido(sessionmaker):
    await add_report(sessionmaker, ReportStatus.CORRIGIDO, ["u1"], updated_at=NOW - timedelta(hours=3))
    await add_report(sessionmaker, ReportStatus.INCOMPLETO, ["u1"], updated_at=NOW - timedelta(hours=1))
    # timestamp anterior ao CORRIGIDO: pela regra de CORRIGIDO nao reanalisaria; INCOMPLETO mais recente manda
    result = await prepare_analysis(sessionmaker, [event("u1", NOW - timedelta(hours=4))], **KW)
    assert [e["uid"] for e in result.events] == ["u1"]


async def test_stale_em_analise_becomes_incomplete_and_is_retried(sessionmaker):
    stale = await add_report(sessionmaker, ReportStatus.EM_ANALISE, ["u1"], updated_at=NOW - timedelta(minutes=45))

    result = await prepare_analysis(sessionmaker, [event("u1", NOW)], **KW)

    reports = {r.id: r for r in await all_reports(sessionmaker)}
    assert reports[stale.id].status == ReportStatus.INCOMPLETO
    assert [e["uid"] for e in result.events] == ["u1"]
    assert reports[result.report_id].attempt_count == 2


async def test_fresh_em_analise_is_not_stale(sessionmaker):
    fresh = await add_report(sessionmaker, ReportStatus.EM_ANALISE, ["u1"], updated_at=NOW - timedelta(minutes=5))
    result = await prepare_analysis(sessionmaker, [event("u1", NOW)], **KW)
    assert result.events == []
    assert next(r for r in await all_reports(sessionmaker) if r.id == fresh.id).status == ReportStatus.EM_ANALISE


async def test_concurrent_batches_analyze_event_once(sessionmaker, monkeypatch):
    from my_agent_app.analysis import dedup

    original = dedup.mark_stale

    async def slow_mark_stale(session, stale_minutes):
        await asyncio.sleep(0.2)  # abre a janela entre o lock e o insert para forcar a corrida
        return await original(session, stale_minutes)

    monkeypatch.setattr(dedup, "mark_stale", slow_mark_stale)
    results = await asyncio.gather(*(prepare_analysis(sessionmaker, [event("u1", NOW)], **KW) for _ in range(5)))

    assert sum(1 for r in results if r.events) == 1
    reports = await all_reports(sessionmaker)
    assert len(reports) == 1 and reports[0].status == ReportStatus.EM_ANALISE


async def test_next_cycle_during_long_analysis_is_ignored(sessionmaker):
    first = await prepare_analysis(sessionmaker, [event("u1", NOW)], **KW)
    second = await prepare_analysis(sessionmaker, [event("u1", NOW)], **KW)
    assert first.events and second.events == []


async def test_handler_calls_analyzer_after_commit_with_only_new_events(sessionmaker):
    await add_report(sessionmaker, ReportStatus.COMPLETO, ["old"])
    seen = {}

    async def analyzer(report_id, events):
        async with sessionmaker() as other:  # outra sessao: so enxerga dados ja commitados
            seen["report"] = (await other.execute(select(Report).where(Report.id == report_id))).scalar_one()
        seen["uids"] = [e["uid"] for e in events]

    await AnalysisHandler(sessionmaker, analyzer, **KW).handle([event("old", NOW), event("new", NOW)])

    assert seen["uids"] == ["new"]
    assert seen["report"].status == ReportStatus.EM_ANALISE and seen["report"].event_uids == ["new"]


async def test_handler_does_not_call_analyzer_when_all_ignored(sessionmaker):
    await add_report(sessionmaker, ReportStatus.COMPLETO, ["u1"])
    calls = []

    async def analyzer(report_id, events):
        calls.append(events)

    await AnalysisHandler(sessionmaker, analyzer, **KW).handle([event("u1", NOW)])
    assert calls == []


async def test_handler_discards_batch_when_database_is_down(caplog):
    broken = async_sessionmaker(create_async_engine("postgresql+asyncpg://x:x@127.0.0.1:1/none"))
    calls = []

    async def analyzer(report_id, events):
        calls.append(events)

    with caplog.at_level(logging.ERROR):
        await AnalysisHandler(broken, analyzer, **KW).handle([event("u1", NOW)])  # nao propaga

    assert calls == [] and "deduplicacao" in caplog.text


async def test_recover_orphans_marks_em_analise_incomplete(sessionmaker):
    orphan = await add_report(sessionmaker, ReportStatus.EM_ANALISE, ["u1"])
    done = await add_report(sessionmaker, ReportStatus.COMPLETO, ["u2"])

    assert await recover_orphans(sessionmaker) == 1

    status = {r.id: r.status for r in await all_reports(sessionmaker)}
    assert status[orphan.id] == ReportStatus.INCOMPLETO and status[done.id] == ReportStatus.COMPLETO


def test_config_defaults_and_overrides(monkeypatch):
    monkeypatch.delenv("ANALYSIS_MAX_ATTEMPTS", raising=False)
    monkeypatch.delenv("ANALYSIS_STALE_TIMEOUT_MINUTES", raising=False)
    assert (get_max_attempts(), get_stale_timeout_minutes()) == (3, 30)
    monkeypatch.setenv("ANALYSIS_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("ANALYSIS_STALE_TIMEOUT_MINUTES", "abc")
    assert (get_max_attempts(), get_stale_timeout_minutes()) == (5, 30)
