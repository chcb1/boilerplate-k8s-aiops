import logging

import pytest

from my_agent_app.agents import mcp
from my_agent_app.agents.mcp import READ_ONLY_TOOLS, filter_read_only, load_read_only_tools
from tests.agents.fakes import make_tool

ALL_TOOLS = [
    "kubectl_get", "kubectl_describe", "kubectl_logs",
    "kubectl_apply", "kubectl_patch", "kubectl_delete", "kubectl_create", "exec_in_pod", "port_forward",
]


class FakeClient:
    instances = []

    def __init__(self, connections, **kwargs):
        self.connections = connections
        FakeClient.instances.append(self)

    async def get_tools(self):
        return [make_tool(name) for name in ALL_TOOLS]


def test_filter_keeps_only_read_only_tools():
    kept = filter_read_only([make_tool(name) for name in ALL_TOOLS])

    assert sorted(t.name for t in kept) == sorted(READ_ONLY_TOOLS)


async def test_load_exposes_exactly_the_read_only_tools(monkeypatch):
    monkeypatch.setattr(mcp, "MultiServerMCPClient", FakeClient)

    tools = await load_read_only_tools("http://mcp:3001/mcp")

    assert sorted(t.name for t in tools) == ["kubectl_describe", "kubectl_get", "kubectl_logs"]
    assert FakeClient.instances[-1].connections == {"kubernetes": {"transport": "http", "url": "http://mcp:3001/mcp"}}


async def test_load_uses_configured_url_by_default(monkeypatch):
    monkeypatch.setattr(mcp, "MultiServerMCPClient", FakeClient)
    monkeypatch.setenv("MCP_SERVER_URL", "http://outro:9/mcp")

    await load_read_only_tools()

    assert FakeClient.instances[-1].connections["kubernetes"]["url"] == "http://outro:9/mcp"


async def test_load_fails_when_no_read_tool_is_exposed(monkeypatch):
    class OnlyWrite(FakeClient):
        async def get_tools(self):
            return [make_tool("kubectl_apply")]

    monkeypatch.setattr(mcp, "MultiServerMCPClient", OnlyWrite)

    with pytest.raises(RuntimeError):
        await load_read_only_tools()


async def test_load_warns_when_some_read_tool_is_missing(monkeypatch, caplog):
    class Partial(FakeClient):
        async def get_tools(self):
            return [make_tool("kubectl_get"), make_tool("kubectl_apply")]

    monkeypatch.setattr(mcp, "MultiServerMCPClient", Partial)

    with caplog.at_level(logging.WARNING):
        tools = await load_read_only_tools()

    assert [t.name for t in tools] == ["kubectl_get"]
    assert "kubectl_describe" in caplog.text


async def test_unavailable_server_raises(monkeypatch):
    class Down(FakeClient):
        async def get_tools(self):
            raise ConnectionError("MCP indisponivel")

    monkeypatch.setattr(mcp, "MultiServerMCPClient", Down)

    with pytest.raises(ConnectionError):
        await load_read_only_tools()
