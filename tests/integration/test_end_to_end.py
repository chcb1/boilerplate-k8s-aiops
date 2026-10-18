from datetime import datetime, timezone

from sqlalchemy import select

from my_agent_app.analysis.handler import AnalysisHandler
from my_agent_app.collector.loop import EventCollector
from my_agent_app.models import Report, ReportStatus

NOW = datetime.now(timezone.utc).isoformat()


def warning(uid: str) -> dict:
    return {"uid": uid, "type": "Warning", "reason": "BackOff", "message": "m", "namespace": "default",
            "involved_object": {"kind": "Pod", "name": "p", "namespace": "default"}, "timestamp": NOW}


class Recorder:
    def __init__(self):
        self.batches: list[list[str]] = []

    async def __call__(self, report_id, events):
        self.batches.append([e["uid"] for e in events])


async def test_new_warning_is_analyzed_once_across_cycles(sessionmaker):
    analyzer = Recorder()
    live = [warning("u1")]

    async def fetch():
        return list(live)

    collector = EventCollector(fetch, AnalysisHandler(sessionmaker, analyzer, max_attempts=3, stale_minutes=30), 60)

    await collector.run_cycle()
    await collector.drain()
    await collector.run_cycle()  # mesmo Warning ainda vivo: lote completo de novo
    await collector.drain()
    live.append(warning("u2"))
    await collector.run_cycle()
    await collector.drain()

    assert analyzer.batches == [["u1"], ["u2"]]


async def test_infrastructure_failure_is_retried_next_cycle(sessionmaker):
    analyzer = Recorder()
    calls = {"n": 0}

    def flaky_sessionmaker():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("banco fora")  # falha antes de existir relatorio
        return sessionmaker()

    async def fetch():
        return [warning("u1")]

    handler = AnalysisHandler(flaky_sessionmaker, analyzer, max_attempts=3, stale_minutes=30)
    collector = EventCollector(fetch, handler, 60)

    await collector.run_cycle()
    await collector.drain()
    assert analyzer.batches == []  # one-shot nao foi perdido: evento segue vivo

    await collector.run_cycle()
    await collector.drain()
    assert analyzer.batches == [["u1"]]


async def test_incomplete_analysis_is_retried_until_the_limit(sessionmaker):
    analyzer = Recorder()

    async def fetch():
        return [warning("u1")]

    collector = EventCollector(fetch, AnalysisHandler(sessionmaker, analyzer, max_attempts=2, stale_minutes=30), 60)

    for _ in range(4):
        await collector.run_cycle()
        await collector.drain()
        async with sessionmaker() as session, session.begin():  # analise termina INCOMPLETA
            for r in (await session.execute(select(Report).where(Report.status == ReportStatus.EM_ANALISE))).scalars():
                r.status = ReportStatus.INCOMPLETO

    assert analyzer.batches == [["u1"], ["u1"]]  # 2 tentativas e para


REPORT = """# Relatorio de Diagnostico Kubernetes

## Problema 1: OOMKilled
- **Severidade:** ALTO
- **Eventos:** u1

### Causa Raiz
Limite de memoria baixo.

## Problema 2: Imagem inexistente
- **Severidade:** CRITICO
- **Eventos:** u2

### Causa Raiz
Tag inexistente.
"""


async def test_collected_batch_becomes_one_report_per_problem_and_is_not_reanalyzed(sessionmaker):
    from functools import partial

    from langchain_core.messages import AIMessage

    from my_agent_app.agents.analyst import run_analysis
    from my_agent_app.analysis.analyzer import RootCauseAnalyzer
    from tests.agents.fakes import ScriptedChatModel, read_only_tools, tool_call

    model = ScriptedChatModel(script=[tool_call("kubectl_describe", {"resource": "pod/p"}), AIMessage(content=REPORT)])

    async def load_tools():
        return read_only_tools()

    analyzer = RootCauseAnalyzer(sessionmaker, load_tools=load_tools, run_agent=partial(run_analysis, model=model))

    async def fetch():
        return [warning("u1"), warning("u2")]

    collector = EventCollector(fetch, AnalysisHandler(sessionmaker, analyzer, max_attempts=3, stale_minutes=30), 60)

    await collector.run_cycle()
    await collector.drain()
    await collector.run_cycle()  # Warnings ainda vivos: entregues de novo, mas ja tratados
    await collector.drain()

    async with sessionmaker() as session:
        reports = list((await session.execute(select(Report))).scalars())
    assert model.calls == 2  # uma unica investigacao (tool + resposta)
    by_uid = {r.event_uids[0]: r for r in reports}
    assert len(reports) == 2
    assert (by_uid["u1"].status, by_uid["u1"].severity) == (ReportStatus.COMPLETO, "ALTO")
    assert (by_uid["u2"].status, by_uid["u2"].severity) == (ReportStatus.COMPLETO, "CRITICO")
    assert "Imagem inexistente" in by_uid["u2"].markdown
