import logging
from collections.abc import Sequence
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import BaseTool
from langgraph.errors import GraphRecursionError

from my_agent_app.agents.config import get_max_iterations, get_model_name
from my_agent_app.agents.prompt import SYSTEM_PROMPT, build_user_message

logger = logging.getLogger(__name__)

# prefixo da mensagem que o ModelCallLimitMiddleware injeta ao encerrar com exit_behavior="end"
LIMIT_MESSAGE_PREFIX = "Model call limits exceeded"
# cada chamada ao modelo consome varios passos do grafo (hooks do middleware, modelo e tools);
# o limite de iteracoes e do middleware, o recursion_limit so precisa ficar acima dele
_STEPS_PER_ITERATION = 4
_RECURSION_MARGIN = 10


@dataclass
class AgentOutcome:
    markdown: str
    limit_reached: bool = False


def _text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text")


def _is_limit_message(message: BaseMessage) -> bool:
    return isinstance(message, AIMessage) and _text(message).startswith(LIMIT_MESSAGE_PREFIX)


def _last_produced_text(messages: Sequence[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not _is_limit_message(message) and _text(message).strip():
            return _text(message)
    return ""


def build_model() -> BaseChatModel:
    return ChatAnthropic(model=get_model_name(), max_retries=3)


async def run_analysis(
    events: list[dict],
    tools: Sequence[BaseTool],
    *,
    model: BaseChatModel | None = None,
    max_iterations: int | None = None,
) -> AgentOutcome:
    """Executa o agente sobre os eventos do lote e devolve o Markdown e se o limite de iteracoes foi atingido."""
    limit = max_iterations if max_iterations is not None else get_max_iterations()
    agent = create_agent(
        model or build_model(),
        list(tools),
        system_prompt=SYSTEM_PROMPT,
        middleware=[ModelCallLimitMiddleware(run_limit=limit, exit_behavior="end")],
    )
    config = {"recursion_limit": limit * _STEPS_PER_ITERATION + _RECURSION_MARGIN}
    try:
        result = await agent.ainvoke({"messages": [HumanMessage(build_user_message(events))]}, config=config)
    except GraphRecursionError:
        logger.warning("Agente excedeu o limite de passos do grafo (%d iteracoes)", limit)
        return AgentOutcome("", limit_reached=True)

    messages = result["messages"]
    if messages and _is_limit_message(messages[-1]):
        logger.warning("Agente atingiu o limite de %d iteracoes sem concluir a investigacao", limit)
        return AgentOutcome(_last_produced_text(messages), limit_reached=True)
    return AgentOutcome(_text(messages[-1]) if messages else "")
