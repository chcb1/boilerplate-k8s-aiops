import pytest

from my_agent_app.agents.analyst import AgentOutcome
from my_agent_app.analysis.analyzer import RootCauseAnalyzer
from my_agent_app.analysis.dedup import prepare_analysis
from my_agent_app.models import ReportStatus
from tests.integration.test_dedup import NOW, all_reports, event

TWO_PROBLEMS = """# Relatorio de Diagnostico Kubernetes

## Problema 1: OOM
- **Severidade:** ALTO
- **Eventos:** u1

### Causa Raiz
Limite de memoria baixo.

---

## Problema 2: Imagem
- **Severidade:** MEDIO
- **Eventos:** u2

### Causa Raiz
Tag inexistente.
"""


async def tools():
    return []


def agent_returning(outcome: AgentOutcome):
    async def run(events, tools):
        return outcome
    return run


def agent_raising(exc: Exception):
    async def run(events, tools):
        raise exc
    return run


async def start(sessionmaker, uids=("u1", "u2")):
    events = [event(uid, NOW) for uid in uids]
    batch = await prepare_analysis(sessionmaker, events, max_attempts=3, stale_minutes=30)
    return batch.report_id, batch.events


async def test_successful_analysis_creates_one_report_per_problem(sessionmaker):
    report_id, events = await start(sessionmaker)
    analyzer = RootCauseAnalyzer(sessionmaker, load_tools=tools, run_agent=agent_returning(AgentOutcome(TWO_PROBLEMS)))

    await analyzer(report_id, events)

    reports = {r.event_uids[0]: r for r in await all_reports(sessionmaker)}
    assert reports["u1"].id == report_id
    assert (reports["u1"].status, reports["u1"].severity) == (ReportStatus.COMPLETO, "ALTO")
    assert (reports["u2"].status, reports["u2"].severity) == (ReportStatus.COMPLETO, "MEDIO")


async def test_next_cycle_ignores_events_already_analyzed(sessionmaker):
    report_id, events = await start(sessionmaker)
    analyzer = RootCauseAnalyzer(sessionmaker, load_tools=tools, run_agent=agent_returning(AgentOutcome(TWO_PROBLEMS)))
    await analyzer(report_id, events)

    again = await prepare_analysis(sessionmaker, events, max_attempts=3, stale_minutes=30)

    assert again.events == []


@pytest.mark.parametrize("failure", ["tools", "agent"])
async def test_infrastructure_failure_marks_batch_incomplete_without_raising(sessionmaker, failure):
    report_id, events = await start(sessionmaker)

    async def broken_tools():
        raise ConnectionError("MCP Server indisponivel")

    analyzer = (
        RootCauseAnalyzer(sessionmaker, load_tools=broken_tools, run_agent=agent_returning(AgentOutcome("x")))
        if failure == "tools"
        else RootCauseAnalyzer(sessionmaker, load_tools=tools, run_agent=agent_raising(TimeoutError("anthropic")))
    )

    await analyzer(report_id, events)

    [report] = await all_reports(sessionmaker)
    assert report.status == ReportStatus.INCOMPLETO and report.event_uids == ["u1", "u2"]


async def test_failed_batch_is_reanalyzed_on_recurrence_and_counts_attempts(sessionmaker):
    report_id, events = await start(sessionmaker)
    analyzer = RootCauseAnalyzer(sessionmaker, load_tools=tools, run_agent=agent_raising(RuntimeError("falha")))
    await analyzer(report_id, events)

    retry = await prepare_analysis(sessionmaker, events, max_attempts=3, stale_minutes=30)

    assert [e["uid"] for e in retry.events] == ["u1", "u2"]
    [new_batch] = [r for r in await all_reports(sessionmaker) if r.status == ReportStatus.EM_ANALISE]
    assert new_batch.attempt_count == 2


async def test_limit_reached_keeps_partial_markdown_as_incomplete(sessionmaker):
    report_id, events = await start(sessionmaker)
    analyzer = RootCauseAnalyzer(
        sessionmaker, load_tools=tools, run_agent=agent_returning(AgentOutcome(TWO_PROBLEMS, limit_reached=True))
    )

    await analyzer(report_id, events)

    [report] = await all_reports(sessionmaker)
    assert report.status == ReportStatus.INCOMPLETO
    assert report.markdown == TWO_PROBLEMS and report.event_uids == ["u1", "u2"]


@pytest.mark.parametrize("response", ["", "Nao consegui formatar o relatorio."])
async def test_response_without_problems_is_incomplete(sessionmaker, response):
    report_id, events = await start(sessionmaker)
    analyzer = RootCauseAnalyzer(sessionmaker, load_tools=tools, run_agent=agent_returning(AgentOutcome(response)))

    await analyzer(report_id, events)

    [report] = await all_reports(sessionmaker)
    assert report.status == ReportStatus.INCOMPLETO and report.markdown == response


async def test_event_omitted_by_the_agent_gets_an_incomplete_report(sessionmaker):
    report_id, events = await start(sessionmaker)
    only_first = TWO_PROBLEMS.split("## Problema 2")[0]
    analyzer = RootCauseAnalyzer(sessionmaker, load_tools=tools, run_agent=agent_returning(AgentOutcome(only_first)))

    await analyzer(report_id, events)

    by_uid = {r.event_uids[0]: r for r in await all_reports(sessionmaker)}
    assert by_uid["u1"].status == ReportStatus.COMPLETO
    assert by_uid["u2"].status == ReportStatus.INCOMPLETO
