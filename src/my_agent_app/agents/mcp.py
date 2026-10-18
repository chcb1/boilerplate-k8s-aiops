import logging
from collections.abc import Iterable

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from my_agent_app.agents.config import get_mcp_server_url

logger = logging.getLogger(__name__)

# lista de permissao: tools novas do MCP Server nao chegam ao agente
READ_ONLY_TOOLS = ("kubectl_get", "kubectl_describe", "kubectl_logs")


def filter_read_only(tools: Iterable[BaseTool]) -> list[BaseTool]:
    return [tool for tool in tools if tool.name in READ_ONLY_TOOLS]


async def load_read_only_tools(url: str | None = None) -> list[BaseTool]:
    """Obtem as tools do MCP Server Kubernetes, mantendo somente as de leitura.

    Levanta excecao se o servidor estiver indisponivel ou nao oferecer nenhuma tool de leitura.
    """
    client = MultiServerMCPClient({"kubernetes": {"transport": "http", "url": url or get_mcp_server_url()}})
    tools = filter_read_only(await client.get_tools())
    missing = set(READ_ONLY_TOOLS) - {tool.name for tool in tools}
    if len(missing) == len(READ_ONLY_TOOLS):
        raise RuntimeError("MCP Server Kubernetes nao expoe nenhuma tool de leitura esperada")
    if missing:
        logger.warning("MCP Server Kubernetes sem as tools: %s", ", ".join(sorted(missing)))
    return tools
