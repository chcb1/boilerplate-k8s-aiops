from collections.abc import Callable
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool, tool


class ScriptedChatModel(BaseChatModel):
    """Modelo falso: devolve respostas roteirizadas. Com `script` vazio e `repeat`, repete a ultima."""

    script: list[AIMessage]
    repeat: bool = False
    seen_messages: list[list[BaseMessage]] = []
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.seen_messages.append(list(messages))
        index = min(self.calls, len(self.script) - 1) if self.repeat else self.calls
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=self.script[index])])


def tool_call(name: str, args: dict, call_id: str = "c1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def make_tool(name: str, handler: Callable[..., str] | None = None) -> BaseTool:
    async def run(resource: str = "") -> str:
        return handler(resource) if handler else f"{name} ok"

    run.__name__ = name
    run.__doc__ = f"Fake {name}"
    return tool(run)


def read_only_tools() -> list[BaseTool]:
    return [make_tool(name) for name in ("kubectl_get", "kubectl_describe", "kubectl_logs")]
