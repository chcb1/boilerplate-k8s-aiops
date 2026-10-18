import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy import select, update
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from my_agent_app.analysis.parser import ParseResult
from my_agent_app.models import Report, ReportStatus

logger = logging.getLogger(__name__)

RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 0.5

# falhas de conexao com o banco; erros de logica (ex.: integridade) nao sao repetidos
_TRANSIENT = (OperationalError, InterfaceError, OSError)

T = TypeVar("T")


async def _retry(operation: Callable[[], Awaitable[T]]) -> T:
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            return await operation()
        except _TRANSIENT as exc:
            if attempt == RETRY_ATTEMPTS:
                raise
            delay = RETRY_BASE_DELAY * 2 ** (attempt - 1)
            logger.warning("Banco indisponivel (%s); nova tentativa %d/%d em %.1fs", exc.__class__.__name__, attempt + 1, RETRY_ATTEMPTS, delay)
            await asyncio.sleep(delay)
    raise AssertionError("inalcancavel")


async def _lock_batch_report(session: AsyncSession, report_id: uuid.UUID) -> Report | None:
    """Relatorio do lote, bloqueado, somente se ainda estiver EM_ANALISE (decisao D3)."""
    stmt = select(Report).where(Report.id == report_id, Report.status == ReportStatus.EM_ANALISE).with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def apply_analysis(
    sessionmaker: async_sessionmaker[AsyncSession],
    report_id: uuid.UUID,
    parsed: ParseResult,
    raw_markdown: str,
) -> bool:
    """Substitui o relatorio EM_ANALISE do lote pelos relatorios por problema, numa transacao.

    Retorna False quando o resultado foi descartado (relatorio ja nao estava EM_ANALISE)
    ou quando o banco falhou definitivamente.
    """

    async def operation() -> bool:
        async with sessionmaker() as session, session.begin():
            batch = await _lock_batch_report(session, report_id)
            if batch is None:
                logger.warning("Relatorio %s nao esta mais EM_ANALISE; resultado do agente descartado", report_id)
                return False

            attempts = batch.attempt_count
            if not parsed.problems:
                batch.status = ReportStatus.INCOMPLETO
                batch.markdown = raw_markdown
                logger.warning("Resposta do agente sem problemas identificaveis; relatorio %s marcado INCOMPLETO", report_id)
                return True

            first, *others = parsed.problems
            batch.markdown = first.markdown
            batch.status = ReportStatus.INCOMPLETO if first.inconclusive else ReportStatus.COMPLETO
            batch.severity = first.severity
            batch.title = first.title
            batch.event_uids = first.event_uids
            for problem in others:
                session.add(
                    Report(
                        markdown=problem.markdown,
                        status=ReportStatus.INCOMPLETO if problem.inconclusive else ReportStatus.COMPLETO,
                        severity=problem.severity,
                        title=problem.title,
                        event_uids=problem.event_uids,
                        attempt_count=attempts,
                    )
                )
            if parsed.unreferenced:
                session.add(
                    Report(status=ReportStatus.INCOMPLETO, event_uids=parsed.unreferenced, attempt_count=attempts)
                )
            return True

    try:
        return await _retry(operation)
    except _TRANSIENT:
        logger.exception(
            "Falha definitiva ao persistir a analise do relatorio %s; Markdown gerado:\n%s", report_id, raw_markdown
        )
        return False


async def mark_incomplete(
    sessionmaker: async_sessionmaker[AsyncSession],
    report_id: uuid.UUID,
    markdown: str = "",
) -> bool:
    """Marca o relatorio do lote como INCOMPLETO, somente se ainda estiver EM_ANALISE."""

    async def operation() -> bool:
        async with sessionmaker() as session, session.begin():
            values: dict = {"status": ReportStatus.INCOMPLETO}
            if markdown:
                values["markdown"] = markdown
            result = await session.execute(
                update(Report).where(Report.id == report_id, Report.status == ReportStatus.EM_ANALISE).values(**values)
            )
            return result.rowcount > 0

    try:
        return await _retry(operation)
    except _TRANSIENT:
        logger.exception(
            "Falha definitiva ao marcar o relatorio %s como INCOMPLETO; Markdown gerado:\n%s", report_id, markdown
        )
        return False
