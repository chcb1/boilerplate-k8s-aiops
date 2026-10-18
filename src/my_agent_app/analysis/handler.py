import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from my_agent_app.analysis.config import get_max_attempts, get_stale_timeout_minutes
from my_agent_app.analysis.dedup import prepare_analysis

logger = logging.getLogger(__name__)

Analyzer = Callable[[UUID, list[dict]], Awaitable[None]]


class AnalysisHandler:
    """Handler do PRD 002: dedup + relatorio EM_ANALISE (insert-first) e so entao o agente."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        analyzer: Analyzer,
        *,
        max_attempts: int | None = None,
        stale_minutes: int | None = None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._analyzer = analyzer
        self._max_attempts = max_attempts if max_attempts is not None else get_max_attempts()
        self._stale_minutes = stale_minutes if stale_minutes is not None else get_stale_timeout_minutes()

    async def handle(self, events: list[dict]) -> None:
        try:
            result = await prepare_analysis(
                self._sessionmaker,
                events,
                max_attempts=self._max_attempts,
                stale_minutes=self._stale_minutes,
            )
        except Exception:
            logger.exception("Falha na deduplicacao; lote descartado (eventos vivos voltam no proximo ciclo)")
            return
        if not result.events:
            return
        try:
            await self._analyzer(result.report_id, result.events)
        except Exception:
            logger.exception("Falha na analise do relatorio %s", result.report_id)
