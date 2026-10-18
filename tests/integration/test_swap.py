import logging
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from my_agent_app.analysis import swap
from my_agent_app.analysis.dedup import prepare_analysis
from my_agent_app.analysis.parser import ParseResult, Problem
from my_agent_app.analysis.swap import apply_analysis, mark_incomplete
from my_agent_app.models import Report, ReportStatus
from tests.integration.test_dedup import NOW, add_report, all_reports, event

KW = dict(max_attempts=3, stale_minutes=30)


def problem(uids, *, severity="ALTO", inconclusive=False, title="p") -> Problem:
    return Problem(title, f"## Problema 1: {title}\nuids {uids}", severity, list(uids), inconclusive)


async def new_batch(sessionmaker, uids, *, attempt_count=1) -> Report:
    return await add_report(sessionmaker, ReportStatus.EM_ANALISE, uids, attempt_count=attempt_count)


async def get(sessionmaker, report_id) -> Report:
    async with sessionmaker() as session:
        return (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()


async def test_batch_report_is_reused_as_first_problem_and_others_inserted(sessionmaker):
    batch = await new_batch(sessionmaker, ["u1", "u2", "u3"], attempt_count=2)
    parsed = ParseResult([problem(["u1"], title="a"), problem(["u2"], severity="MEDIO", title="b"),
                          problem(["u3"], severity="BAIXO", title="c")])

    assert await apply_analysis(sessionmaker, batch.id, parsed, "raw") is True

    reports = {r.event_uids[0]: r for r in await all_reports(sessionmaker)}
    assert len(reports) == 3
    assert reports["u1"].id == batch.id and reports["u1"].created_at == batch.created_at
    assert {r.status for r in reports.values()} == {ReportStatus.COMPLETO}
    assert {u: r.severity for u, r in reports.items()} == {"u1": "ALTO", "u2": "MEDIO", "u3": "BAIXO"}
    assert {r.attempt_count for r in reports.values()} == {2}
    assert reports["u2"].markdown.startswith("## Problema 1: b")


async def test_unreferenced_uids_go_to_an_incomplete_report_with_inherited_attempts(sessionmaker):
    batch = await new_batch(sessionmaker, ["u1", "u2"], attempt_count=2)
    parsed = ParseResult([problem(["u1"])], unreferenced=["u2"])

    await apply_analysis(sessionmaker, batch.id, parsed, "raw")

    by_status = {r.status: r for r in await all_reports(sessionmaker)}
    assert by_status[ReportStatus.COMPLETO].event_uids == ["u1"]
    assert by_status[ReportStatus.INCOMPLETO].event_uids == ["u2"]
    assert by_status[ReportStatus.INCOMPLETO].attempt_count == 2


async def test_inconclusive_problem_is_incomplete(sessionmaker):
    batch = await new_batch(sessionmaker, ["u1"])

    await apply_analysis(sessionmaker, batch.id, ParseResult([problem(["u1"], inconclusive=True)]), "raw")

    assert (await get(sessionmaker, batch.id)).status == ReportStatus.INCOMPLETO


async def test_inherited_attempt_count_enforces_the_limit(sessionmaker):
    await add_report(sessionmaker, ReportStatus.INCOMPLETO, ["u1"], attempt_count=2)
    first = await prepare_analysis(sessionmaker, [event("u1", NOW)], **KW)
    assert [e["uid"] for e in first.events] == ["u1"]  # tentativa 3

    await apply_analysis(sessionmaker, first.report_id, ParseResult([problem(["u1"], inconclusive=True)]), "raw")

    again = await prepare_analysis(sessionmaker, [event("u1", NOW)], **KW)
    assert again.events == []  # limite de 3 atingido: nao reanalisa


async def test_unreferenced_event_counts_toward_the_attempt_limit(sessionmaker):
    await add_report(sessionmaker, ReportStatus.INCOMPLETO, ["u1"], attempt_count=1)
    batch = await prepare_analysis(sessionmaker, [event("u1", NOW), event("u2", NOW)], **KW)
    await apply_analysis(sessionmaker, batch.report_id, ParseResult([problem(["u1"])], ["u2"]), "raw")

    second = await prepare_analysis(sessionmaker, [event("u2", NOW)], **KW)
    assert [e["uid"] for e in second.events] == ["u2"]  # INCOMPLETO volta por presenca
    assert (await get(sessionmaker, second.report_id)).attempt_count == 3
    await apply_analysis(sessionmaker, second.report_id, ParseResult([], ["u2"]), "raw")

    third = await prepare_analysis(sessionmaker, [event("u2", NOW)], **KW)
    assert third.events == []  # sem relatorio proprio, mas com teto de tentativas


async def test_result_is_discarded_when_batch_report_left_em_analise(sessionmaker):
    batch = await new_batch(sessionmaker, ["u1"])
    assert await mark_incomplete(sessionmaker, batch.id) is True  # estagnacao/startup durante a analise

    assert await apply_analysis(sessionmaker, batch.id, ParseResult([problem(["u1"])]), "raw") is False

    [report] = await all_reports(sessionmaker)
    assert report.status == ReportStatus.INCOMPLETO and report.markdown == ""


async def test_response_without_problems_marks_batch_incomplete_keeping_raw(sessionmaker):
    batch = await new_batch(sessionmaker, ["u1", "u2"])

    await apply_analysis(sessionmaker, batch.id, ParseResult([], ["u1", "u2"]), "resposta sem formato")

    [report] = await all_reports(sessionmaker)
    assert report.status == ReportStatus.INCOMPLETO
    assert report.markdown == "resposta sem formato"
    assert report.event_uids == ["u1", "u2"]


async def test_mark_incomplete_only_touches_em_analise(sessionmaker):
    done = await add_report(sessionmaker, ReportStatus.CORRIGINDO, ["u1"])

    assert await mark_incomplete(sessionmaker, done.id, "x") is False

    assert (await get(sessionmaker, done.id)).status == ReportStatus.CORRIGINDO


async def test_mark_incomplete_preserves_given_markdown(sessionmaker):
    batch = await new_batch(sessionmaker, ["u1"])

    assert await mark_incomplete(sessionmaker, batch.id, "parcial") is True

    row = await get(sessionmaker, batch.id)
    assert row.status == ReportStatus.INCOMPLETO and row.markdown == "parcial"


class Flaky:
    """sessionmaker que falha `failures` vezes com erro de conexao antes de funcionar."""

    def __init__(self, real, failures):
        self.real, self.failures, self.calls = real, failures, 0

    def __call__(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))
        return self.real()


@pytest.fixture
def fast_retry(monkeypatch):
    monkeypatch.setattr(swap, "RETRY_BASE_DELAY", 0)


async def test_transient_db_failure_is_retried(sessionmaker, fast_retry):
    batch = await new_batch(sessionmaker, ["u1"])
    flaky = Flaky(sessionmaker, failures=2)

    assert await apply_analysis(flaky, batch.id, ParseResult([problem(["u1"])]), "raw") is True

    assert flaky.calls == 3
    assert (await get(sessionmaker, batch.id)).status == ReportStatus.COMPLETO


async def test_definitive_db_failure_logs_markdown_and_does_not_raise(sessionmaker, fast_retry, caplog):
    batch = await new_batch(sessionmaker, ["u1"])
    flaky = Flaky(sessionmaker, failures=99)

    with caplog.at_level(logging.ERROR):
        assert await apply_analysis(flaky, batch.id, ParseResult([problem(["u1"])]), "# markdown gerado") is False

    assert flaky.calls == swap.RETRY_ATTEMPTS
    assert "# markdown gerado" in caplog.text
    assert (await get(sessionmaker, batch.id)).status == ReportStatus.EM_ANALISE


async def test_mark_incomplete_definitive_failure_logs_markdown(sessionmaker, fast_retry, caplog):
    batch = await new_batch(sessionmaker, ["u1"])

    with caplog.at_level(logging.ERROR):
        assert await mark_incomplete(Flaky(sessionmaker, 99), batch.id, "# parcial") is False

    assert "# parcial" in caplog.text
