
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
