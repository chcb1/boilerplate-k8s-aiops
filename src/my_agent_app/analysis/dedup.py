import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from my_agent_app.models import ACTIVE_STATUSES, Report, ReportStatus

logger = logging.getLogger(__name__)

# chave do advisory lock que serializa "dedup + insert do EM_ANALISE"
DEDUP_LOCK_KEY = 7_001_002


@dataclass
class DedupResult:
    events: list[dict] = field(default_factory=list)
    report_id: uuid.UUID | None = None


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _classify(event: dict, reports: list[Report], max_attempts: int) -> tuple[bool, int]:
    """Decide se o evento deve ser analisado.

    Retorna (analisar, tentativas_anteriores); tentativas_anteriores so conta
    quando a decisao veio da regra de INCOMPLETO.
    """
    if not reports:
        return True, 0
    if any(r.status in ACTIVE_STATUSES for r in reports):
        return False, 0

    latest = max(reports, key=lambda r: r.updated_at)
    if latest.status == ReportStatus.CORRIGIDO:
        return _parse_timestamp(event["timestamp"]) > latest.updated_at, 0

    previous = max(r.attempt_count for r in reports if r.status == ReportStatus.INCOMPLETO)
    if previous >= max_attempts:
        logger.warning(
            "Evento %s atingiu o limite de %d tentativas de analise; nao sera reanalisado",
            event["uid"],
            max_attempts,
        )
        return False, previous
    return True, previous


async def mark_stale(session: AsyncSession, stale_minutes: int) -> int:
    result = await session.execute(
        update(Report)
        .where(
            Report.status == ReportStatus.EM_ANALISE,
            Report.updated_at < func.now() - timedelta(minutes=stale_minutes),
        )
        .values(status=ReportStatus.INCOMPLETO)
    )
    return result.rowcount


async def prepare_analysis(
    sessionmaker: async_sessionmaker[AsyncSession],
    events: list[dict],
    *,
    max_attempts: int,
    stale_minutes: int,
) -> DedupResult:
    """Deduplica o lote e cria o relatorio EM_ANALISE na mesma transacao (insert-first)."""
    uids = [e["uid"] for e in events]
    async with sessionmaker() as session, session.begin():
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": DEDUP_LOCK_KEY})

        stale = await mark_stale(session, stale_minutes)
        if stale:
            logger.warning("%d relatorio(s) EM_ANALISE estagnado(s) marcado(s) como INCOMPLETO", stale)

        rows = (await session.execute(select(Report).where(Report.event_uids.overlap(uids)))).scalars().all()

        selected: list[dict] = []
        previous_attempts = 0
        for event in events:
            related = [r for r in rows if event["uid"] in r.event_uids]
            analyze, previous = _classify(event, related, max_attempts)
            if analyze:
                selected.append(event)
                previous_attempts = max(previous_attempts, previous)

        if not selected:
            return DedupResult()

        report = Report(
            status=ReportStatus.EM_ANALISE,
            event_uids=[e["uid"] for e in selected],
            attempt_count=previous_attempts + 1,
        )
        session.add(report)
    return DedupResult(events=selected, report_id=report.id)


async def recover_orphans(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    """No startup, marca como INCOMPLETO os EM_ANALISE interrompidos por crash/restart."""
    async with sessionmaker() as session, session.begin():
        result = await session.execute(
            update(Report).where(Report.status == ReportStatus.EM_ANALISE).values(status=ReportStatus.INCOMPLETO)
        )
    if result.rowcount:
        logger.warning("%d relatorio(s) EM_ANALISE orfao(s) marcado(s) como INCOMPLETO no startup", result.rowcount)
    return result.rowcount
