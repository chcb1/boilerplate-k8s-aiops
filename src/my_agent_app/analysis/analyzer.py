import logging
from collections.abc import Awaitable, Callable, Sequence
from uuid import UUID

from langchain_core.tools import BaseTool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from my_agent_app.agents.analyst import AgentOutcome, run_analysis
from my_agent_app.agents.mcp import load_read_only_tools
from my_agent_app.analysis.parser import parse_report
from my_agent_app.analysis.swap import apply_analysis, mark_incomplete

logger = logging.getLogger(__name__)

LoadTools = Callable[[], Awaitable[Sequence[BaseTool]]]
RunAgent = Callable[[list[dict], Sequence[BaseTool]], Awaitable[AgentOutcome]]


class RootCauseAnalyzer:
    """Analyzer do `AnalysisHandler`: roda o agente sobre o lote e persiste o resultado.

    Qualquer falha de infraestrutura (MCP, API do Claude) deixa o relatorio do lote INCOMPLETO
    e nao se propaga; o evento volta pela regra de reanalise de INCOMPLETO.
    """

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        load_tools: LoadTools = load_read_only_tools,
        run_agent: RunAgent = run_analysis,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._load_tools = load_tools
        self._run_agent = run_agent

    async def __call__(self, report_id: UUID, events: list[dict]) -> None:
        try:
            tools = await self._load_tools()
            outcome = await self._run_agent(events, tools)
        except Exception:
            logger.exception("Falha de infraestrutura na analise do relatorio %s; marcando INCOMPLETO", report_id)
            await mark_incomplete(self._sessionmaker, report_id)
            return

        if outcome.limit_reached:
            await mark_incomplete(self._sessionmaker, report_id, outcome.markdown)
            return

        parsed = parse_report(outcome.markdown, [event["uid"] for event in events])
        await apply_analysis(self._sessionmaker, report_id, parsed, outcome.markdown)
