from my_agent_app.agents.prompt import SYSTEM_PROMPT, build_user_message
from my_agent_app.analysis.parser import parse_report

RESPONSE = """# Relatorio de Diagnostico Kubernetes

## Problema 1: Deployment sem memoria
- **Severidade:** ALTO
- **Namespace:** app
- **Recursos Afetados:** deployment/api
- **Eventos:** u1

### Causa Raiz
Limite de memoria baixo.

### Evidencias
- OOMKilled

### Solucao Recomendada
Aumentar o limite.

### Comando Sugerido
```bash
kubectl patch deployment api -n app --type=merge -p '{"spec":{"x":"*y*"}}'
```
"""


def test_prompt_asks_for_the_suggested_command_in_a_fenced_block():
    after = SYSTEM_PROMPT.split("### Comando Sugerido", 1)[1]
    assert "```bash\nkubectl patch" in after
    assert after.count("```") >= 2


def test_prompt_keeps_the_sections_the_parser_depends_on():
    for marker in ("## Problema 1:", "**Severidade:**", "**Eventos:**", "### Causa Raiz"):
        assert marker in SYSTEM_PROMPT


def test_parser_still_extracts_fields_when_the_command_is_fenced():
    [problem] = parse_report(RESPONSE, ["u1"]).problems

    assert problem.title == "Deployment sem memoria"
    assert problem.severity == "ALTO"
    assert problem.event_uids == ["u1"]
    assert not problem.inconclusive
    assert "```bash" in problem.markdown and "*y*" in problem.markdown


def test_user_message_still_lists_events():
    assert '"uid": "u1"' in build_user_message([{"uid": "u1"}])
