import asyncio

from sqlalchemy import select, update

from my_agent_app.models import Report, ReportStatus


async def _insert(sessionmaker) -> Report:
    async with sessionmaker() as session, session.begin():
        report = Report(status=ReportStatus.EM_ANALISE, event_uids=["u1", "u2"])
        session.add(report)
    return report


async def test_defaults(sessionmaker):
    report = await _insert(sessionmaker)
    async with sessionmaker() as session:
        row = (await session.execute(select(Report).where(Report.id == report.id))).scalar_one()
    assert row.attempt_count == 1
    assert row.markdown == ""
    assert row.event_uids == ["u1", "u2"]
    assert row.created_at == row.updated_at


async def test_updated_at_changes_on_core_status_update(sessionmaker):
    report = await _insert(sessionmaker)
    await asyncio.sleep(0.05)
    async with sessionmaker() as session, session.begin():
        await session.execute(
            update(Report).where(Report.id == report.id).values(status=ReportStatus.COMPLETO)
        )
    async with sessionmaker() as session:
        row = (await session.execute(select(Report).where(Report.id == report.id))).scalar_one()
    assert row.status == ReportStatus.COMPLETO
    assert row.updated_at > row.created_at


async def test_updated_at_changes_on_orm_status_update(sessionmaker):
    report = await _insert(sessionmaker)
    await asyncio.sleep(0.05)
    async with sessionmaker() as session, session.begin():
        row = (await session.execute(select(Report).where(Report.id == report.id))).scalar_one()
        row.status = ReportStatus.INCOMPLETO
    async with sessionmaker() as session:
        row = (await session.execute(select(Report).where(Report.id == report.id))).scalar_one()
    assert row.updated_at > row.created_at


async def test_event_uids_overlap_query(sessionmaker):
    await _insert(sessionmaker)
    async with sessionmaker() as session:
        hit = (await session.execute(select(Report).where(Report.event_uids.overlap(["u2", "zz"])))).scalars().all()
        miss = (await session.execute(select(Report).where(Report.event_uids.overlap(["zz"])))).scalars().all()
    assert len(hit) == 1 and miss == []
