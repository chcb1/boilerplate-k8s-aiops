import logging

import pytest

from my_agent_app.agents.config import (
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_MODEL_NAME,
    get_max_iterations,
    get_mcp_server_url,
    get_model_name,
)


def test_max_iterations_default_when_unset(monkeypatch):
    monkeypatch.delenv("AGENT_MAX_ITERATIONS", raising=False)
    assert get_max_iterations() == DEFAULT_MAX_ITERATIONS == 25


def test_max_iterations_valid_value(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "10")
    assert get_max_iterations() == 10


@pytest.mark.parametrize("raw", ["abc", "0", "-3"])
def test_max_iterations_invalid_falls_back_and_warns(monkeypatch, caplog, raw):
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", raw)
    with caplog.at_level(logging.WARNING):
        assert get_max_iterations() == 25
    assert "AGENT_MAX_ITERATIONS" in caplog.text


def test_model_name_default_and_override(monkeypatch):
    monkeypatch.delenv("AGENT_MODEL_NAME", raising=False)
    assert get_model_name() == DEFAULT_MODEL_NAME == "claude-haiku-4-5"
    monkeypatch.setenv("AGENT_MODEL_NAME", "claude-sonnet-5-5")
    assert get_model_name() == "claude-sonnet-5-5"


def test_mcp_server_url_default_and_override(monkeypatch):
    monkeypatch.delenv("MCP_SERVER_URL", raising=False)
    assert get_mcp_server_url() == "http://localhost:3001/mcp"
    monkeypatch.setenv("MCP_SERVER_URL", "http://mcp:3001/mcp")
    assert get_mcp_server_url() == "http://mcp:3001/mcp"
