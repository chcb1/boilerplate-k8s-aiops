
from sqlalchemy import select

from my_agent_app import main
from my_agent_app.models import Report, ReportStatus
from tests.integration.conftest import TEST_URL


class FakeCluster:
    async def fetch(self):
        return []


async def test_lifespan_marks_orphaned_em_analise_as_incomplete(sessionmaker, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_URL)
    monkeypatch.setattr(main, "ClusterEvents", FakeCluster)
    async with sessionmaker() as session, session.begin():
        orphan = Report(status=ReportStatus.EM_ANALISE, event_uids=["u1"])
        session.add(orphan)

    async with main.lifespan(main.app):
        pass  # restart simulado: startup + shutdown

    async with sessionmaker() as session:
        row = (await session.execute(select(Report).where(Report.id == orphan.id))).scalar_one()
    assert row.status == ReportStatus.INCOMPLETO


async def test_lifespan_wires_the_analysis_handler_into_the_collector(sessionmaker, monkeypatch):
    from my_agent_app.analysis.handler import AnalysisHandler

    captured = {}

    class RecordingCollector:
        def __init__(self, fetch, handler):
            captured["handler"] = handler

        async def run(self):
            pass

    monkeypatch.setenv("DATABASE_URL", TEST_URL)
    monkeypatch.setattr(main, "ClusterEvents", FakeCluster)
    monkeypatch.setattr(main, "EventCollector", RecordingCollector)

    async with main.lifespan(main.app):
        pass

    assert isinstance(captured["handler"], AnalysisHandler)
