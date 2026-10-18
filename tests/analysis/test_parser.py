import logging

import pytest

from my_agent_app.analysis.parser import parse_report

HEADER = """# Relatorio de Diagnostico Kubernetes

## Resumo
| Total | Criticos | Altos | Medios | Baixos |
|-------|----------|-------|--------|--------|
| 2     | 0        | 1     | 1      | 0      |

---
"""


def problem(n: int, severity: str, events: str, root_cause: str = "OOMKilled por limite baixo.") -> str:
    return f"""## Problema {n}: causa {n}
- **Severidade:** {severity}
- **Namespace:** default
- **Recursos Afetados:** pod/p{n}
- **Eventos:** {events}

### Causa Raiz
{root_cause}

### Evidencias
- evidencia

### Solucao Recomendada
Ajustar.

---
"""


def test_single_problem():
    result = parse_report(HEADER + problem(1, "ALTO", "u1, u2"), ["u1", "u2"])

    [p] = result.problems
    assert p.title == "causa 1"
    assert p.severity == "ALTO"
    assert p.event_uids == ["u1", "u2"]
    assert not p.inconclusive
    assert p.markdown.startswith("## Problema 1: causa 1")
    assert "Resumo" not in p.markdown
    assert result.unreferenced == []


def test_multiple_problems_split_by_section():
    result = parse_report(HEADER + problem(1, "ALTO", "u1") + problem(2, "MEDIO", "u2"), ["u1", "u2"])

    assert [p.event_uids for p in result.problems] == [["u1"], ["u2"]]
    assert [p.severity for p in result.problems] == ["ALTO", "MEDIO"]
    assert "Problema 2" not in result.problems[0].markdown


@pytest.mark.parametrize("raw,expected", [
    ("CRITICO", "CRITICO"),
    ("CRÍTICO", "CRITICO"),
    ("médio", "MEDIO"),
    ("**BAIXO**", "BAIXO"),
    ("CRITICO | ALTO | MEDIO | BAIXO", "CRITICO"),
])
def test_severity_is_normalized(raw, expected):
    [p] = parse_report(problem(1, raw, "u1"), ["u1"]).problems
    assert p.severity == expected


@pytest.mark.parametrize("raw", ["GRAVISSIMO", ""])
def test_invalid_severity_is_empty_and_warns(caplog, raw):
    with caplog.at_level(logging.WARNING):
        [p] = parse_report(problem(1, raw, "u1"), ["u1"]).problems
    assert p.severity is None
    assert "severidade" in caplog.text


def test_missing_severity_line():
    text = problem(1, "ALTO", "u1").replace("- **Severidade:** ALTO\n", "")
    [p] = parse_report(text, ["u1"]).problems
    assert p.severity is None


@pytest.mark.parametrize("cause", ["Inconclusiva: sem logs.", "**Inconclusiva**", "inconclusivo", "INCONCLUSIVA"])
def test_inconclusive_root_cause(cause):
    [p] = parse_report(problem(1, "ALTO", "u1", cause), ["u1"]).problems
    assert p.inconclusive


def test_conclusive_root_cause_mentioning_the_word_later():
    [p] = parse_report(problem(1, "ALTO", "u1", "Imagem inexistente. Nao e inconclusiva."), ["u1"]).problems
    assert not p.inconclusive


@pytest.mark.parametrize("events", [
    "u1,u2,u3",
    "u1, u2, u3",
    "u1 u2 u3",
    "`u1`, `u2`, `u3`",
    "u1;u2;u3",
    "u1\nu2\nu3",
    "u1\n  - u2\n  - u3",
])
def test_uid_separators(events):
    [p] = parse_report(problem(1, "ALTO", events), ["u1", "u2", "u3"]).problems
    assert p.event_uids == ["u1", "u2", "u3"]


def test_uid_with_dashes_is_kept_whole():
    uid = "4f1c2b9e-6a1d-4e7b-9c1f-2d8e5a7b3c10"
    [p] = parse_report(problem(1, "ALTO", f"{uid}"), [uid]).problems
    assert p.event_uids == [uid]


def test_unknown_uid_is_ignored_and_warns(caplog):
    with caplog.at_level(logging.WARNING):
        [p] = parse_report(problem(1, "ALTO", "u1, inventado"), ["u1"]).problems
    assert p.event_uids == ["u1"]
    assert "inventado" in caplog.text


def test_repeated_uid_stays_in_first_problem(caplog):
    with caplog.at_level(logging.WARNING):
        result = parse_report(problem(1, "ALTO", "u1, u2") + problem(2, "MEDIO", "u2, u3"), ["u1", "u2", "u3"])
    assert [p.event_uids for p in result.problems] == [["u1", "u2"], ["u3"]]
    assert "mais de um problema" in caplog.text


def test_unreferenced_uids_are_reported(caplog):
    with caplog.at_level(logging.WARNING):
        result = parse_report(problem(1, "ALTO", "u1"), ["u1", "u2", "u3"])
    assert result.unreferenced == ["u2", "u3"]
    assert "nao foram referenciados" in caplog.text


def test_problem_without_valid_uid_is_dropped(caplog):
    with caplog.at_level(logging.WARNING):
        result = parse_report(problem(1, "ALTO", "inventado") + problem(2, "MEDIO", "u1"), ["u1", "u2"])
    assert [p.event_uids for p in result.problems] == [["u1"]]
    assert result.unreferenced == ["u2"]
    assert "descartado" in caplog.text


@pytest.mark.parametrize("response", ["", "   \n", "Nao consegui concluir.", HEADER])
def test_response_without_problems(response):
    result = parse_report(response, ["u1", "u2"])
    assert result.problems == []
    assert result.unreferenced == ["u1", "u2"]


def test_none_response_is_treated_as_empty():
    assert parse_report(None, ["u1"]).problems == []


def test_title_is_extracted_from_the_heading():
    [p] = parse_report(problem(1, "ALTO", "u1"), ["u1"]).problems
    assert p.title == "causa 1"


def test_long_title_is_truncated_to_the_column_size():
    text = problem(1, "ALTO", "u1").replace("causa 1", "x" * 400)
    [p] = parse_report(text, ["u1"]).problems
    assert p.title == "x" * 255


def test_empty_title_falls_back_to_the_problem_number():
    text = problem(1, "ALTO", "u1").replace("## Problema 1: causa 1", "## Problema 1:")
    [p] = parse_report(text, ["u1"]).problems
    assert p.title == "Problema 1"
