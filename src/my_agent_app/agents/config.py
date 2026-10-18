import os

from my_agent_app.analysis.config import positive_int

DEFAULT_MODEL_NAME = "claude-haiku-4-5"
DEFAULT_MAX_ITERATIONS = 25
DEFAULT_MCP_SERVER_URL = "http://localhost:3001/mcp"


def get_model_name() -> str:
    return os.environ.get("AGENT_MODEL_NAME", "").strip() or DEFAULT_MODEL_NAME


def get_max_iterations() -> int:
    return positive_int("AGENT_MAX_ITERATIONS", DEFAULT_MAX_ITERATIONS)


def get_mcp_server_url() -> str:
    return os.environ.get("MCP_SERVER_URL", "").strip() or DEFAULT_MCP_SERVER_URL
