import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from my_agent_app.agents.analyst import run_analysis
from tests.agents.fakes import ScriptedChatModel, make_tool, read_only_tools, tool_call

EVENTS = [{"uid": "u1", "type": "Warning", "reason": "BackOff", "message": "m", "namespace": "default",
           "involved_object": {"kind": "Pod", "name": "p", "namespace": "default"}, "timestamp": "2026-10-18T10:00:00+00:00"}]
REPORT = "# Relatorio de Diagnostico Kubernetes\n\n## Problema 1: x\n- **Eventos:** u1\n"


async def test_agent_investigates_with_tools_and_returns_report():
    called = []
    tools = [make_tool("kubectl_describe", lambda r: called.append(r) or "Reason: OOMKilled"),
             make_tool("kubectl_get"), make_tool("kubectl_logs")]
    model = ScriptedChatModel(script=[tool_call("kubectl_describe", {"resource": "pod/p"}), AIMessage(content=REPORT)])

    outcome = await run_analysis(EVENTS, tools, model=model, max_iterations=10)

    assert outcome.markdown == REPORT and not outcome.limit_reached
    assert called == ["pod/p"]
    first_call = model.seen_messages[0]
    assert isinstance(first_call[0], SystemMessage) and "NUNCA execute kubectl_patch" in first_call[0].content
    user = next(m for m in first_call if isinstance(m, HumanMessage))
    assert json.dumps(EVENTS[0], ensure_ascii=False) in user.content
    assert any("OOMKilled" in str(m.content) for m in model.seen_messages[1])  # resultado da tool volta ao modelo


async def test_text_blocks_are_joined():
    blocks = [{"type": "text", "text": "# Rel"}, {"type": "text", "text": "atorio"}]
    model = ScriptedChatModel(script=[AIMessage(content=blocks)])

    outcome = await run_analysis(EVENTS, read_only_tools(), model=model, max_iterations=5)

    assert outcome.markdown == "# Relatorio"


async def test_limit_reached_keeps_what_the_agent_produced():
    looping = AIMessage(content="parcial", tool_calls=[{"name": "kubectl_get", "args": {"resource": "x"}, "id": "c"}])
    model = ScriptedChatModel(script=[looping], repeat=True)

    outcome = await run_analysis(EVENTS, read_only_tools(), model=model, max_iterations=3)

    assert outcome.limit_reached
    assert outcome.markdown == "parcial"
    assert model.calls == 3


async def test_limit_reached_without_any_text():
    model = ScriptedChatModel(script=[tool_call("kubectl_get", {"resource": "x"})], repeat=True)

    outcome = await run_analysis(EVENTS, read_only_tools(), model=model, max_iterations=2)

    assert outcome.limit_reached and outcome.markdown == ""


async def test_finishing_exactly_on_the_last_allowed_iteration_is_not_a_limit():
    model = ScriptedChatModel(script=[tool_call("kubectl_get", {"resource": "x"}), AIMessage(content=REPORT)])

    outcome = await run_analysis(EVENTS, read_only_tools(), model=model, max_iterations=2)

    assert outcome.markdown == REPORT and not outcome.limit_reached


async def test_default_limit_comes_from_environment(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "2")
    model = ScriptedChatModel(script=[tool_call("kubectl_get", {"resource": "x"})], repeat=True)

    outcome = await run_analysis(EVENTS, read_only_tools(), model=model)

    assert outcome.limit_reached and model.calls == 2


async def test_default_limit_of_25_is_not_cut_by_the_graph_recursion_limit():
    model = ScriptedChatModel(script=[tool_call("kubectl_get", {"resource": "x"})], repeat=True)

    outcome = await run_analysis(EVENTS, read_only_tools(), model=model)

    assert outcome.limit_reached and model.calls == 25
