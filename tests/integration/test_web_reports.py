import re
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event

from my_agent_app import main
from my_agent_app.models import Report, ReportStatus

BASE = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def client(sessionmaker):
    main.app.state.sessionmaker = sessionmaker  # sem lifespan: o coletor nao sobe nos testes
    transport = httpx.ASGITransport(app=main.app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def add(sessionmaker, *, minutes=0, status=ReportStatus.COMPLETO, title="Problema", severity="ALTO",
              markdown="", uids=("u1",), attempts=1) -> Report:
    created = BASE + timedelta(minutes=minutes)
    async with sessionmaker() as session, session.begin():
        report = Report(status=status, title=title, severity=severity, markdown=markdown, event_uids=list(uids),
                        attempt_count=attempts, created_at=created, updated_at=created)
        session.add(report)
    return report


def rows(html: str) -> list[str]:
    return re.findall(r"<tr>\s*<td>(.*?)</tr>", html, re.S)


async def test_list_is_ordered_by_creation_most_recent_first(client, sessionmaker):
    await add(sessionmaker, minutes=0, title="antigo")
    await add(sessionmaker, minutes=30, title="recente")
    await add(sessionmaker, minutes=10, title="meio")

    html = (await client.get("/reports")).text

    assert [t for t in ("recente", "meio", "antigo") if t in html] == ["recente", "meio", "antigo"]
    assert html.index("recente") < html.index("meio") < html.index("antigo")


async def test_list_shows_title_link_severity_status_date_and_short_id(client, sessionmaker):
    report = await add(sessionmaker, title="Pod em OOMKilled", severity="CRITICO", status=ReportStatus.COMPLETO)

    response = await client.get("/reports")

    assert response.status_code == 200
    html = response.text
    assert f'<a href="/reports/{report.id}">Pod em OOMKilled</a>' in html
    assert "sev-critico" in html and ">CRITICO<" in html
    assert "badge-complete" in html and ">COMPLETO<" in html
    assert "18/10/2026 12:00 UTC" in html
    assert str(report.id)[:8] in html


@pytest.mark.parametrize("status,css", [
    (ReportStatus.EM_ANALISE, "badge-processing"),
    (ReportStatus.COMPLETO, "badge-complete"),
    (ReportStatus.INCOMPLETO, "badge-incomplete"),
    (ReportStatus.CORRIGINDO, "badge-executing"),
    (ReportStatus.CORRIGIDO, "badge-executed"),
    (ReportStatus.FALHA_CORRECAO, "badge-execution-failed"),
])
async def test_status_badge_class_by_status(client, sessionmaker, status, css):
    await add(sessionmaker, status=status)

    html = (await client.get("/reports")).text

    assert f'class="badge {css}">{status.value}</span>' in html


async def test_report_without_severity_shows_absence_marker(client, sessionmaker):
    await add(sessionmaker, severity=None, status=ReportStatus.INCOMPLETO, title=None)

    html = (await client.get("/reports")).text

    assert '<span class="muted">—</span>' in html
    assert "sev-" not in html.split("<tbody>")[1]


@pytest.mark.parametrize("status,expected", [
    (ReportStatus.EM_ANALISE, "Análise em andamento"),
    (ReportStatus.INCOMPLETO, "Análise incompleta ("),
    (ReportStatus.COMPLETO, "Relatório "),
])
async def test_report_without_title_gets_a_fallback(client, sessionmaker, status, expected):
    report = await add(sessionmaker, title=None, status=status)

    html = (await client.get("/reports")).text

    assert expected in html
    assert f'href="/reports/{report.id}"' in html
    assert "None" not in html


async def test_empty_list_shows_message_and_no_table(client):
    response = await client.get("/reports")

    assert response.status_code == 200
    assert "Nenhum relatório encontrado" in response.text
    assert "<table" not in response.text


async def test_list_is_capped_at_200_with_notice(client, sessionmaker):
    async with sessionmaker() as session, session.begin():
        session.add_all(
            Report(status=ReportStatus.COMPLETO, title=f"r{i}", event_uids=[f"u{i}"],
                   created_at=BASE + timedelta(minutes=i), updated_at=BASE)
            for i in range(201)
        )

    html = (await client.get("/reports")).text

    assert len(rows(html)) == 200
    assert "r200" in html and ">r0<" not in html  # o mais antigo ficou de fora
    assert "200 relatórios mais recentes" in html


async def test_list_at_exactly_200_has_no_notice(client, sessionmaker):
    async with sessionmaker() as session, session.begin():
        session.add_all(
            Report(status=ReportStatus.COMPLETO, title=f"r{i}", event_uids=[f"u{i}"],
                   created_at=BASE + timedelta(minutes=i), updated_at=BASE)
            for i in range(200)
        )

    html = (await client.get("/reports")).text

    assert len(rows(html)) == 200 and "mais recentes" not in html


async def test_list_query_does_not_load_the_markdown(client, sessionmaker):
    await add(sessionmaker, markdown="# conteudo grande")
    statements = []
    engine = sessionmaker.kw["bind"].sync_engine

    def capture(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        await client.get("/reports")
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT") and "FROM reports" in s]
    assert selects and all("reports.markdown" not in s for s in selects)


FULL_REPORT = """## Problema 1: Pod em OOMKilled
- **Severidade:** ALTO
- **Eventos:** u1

### Causa Raiz
Limite de memoria baixo.

### Evidencias
- container reiniciado 12 vezes
- `OOMKilled` no ultimo estado

| Recurso | Limite |
|---------|--------|
| api     | 64Mi   |

### Comando Sugerido
```bash
kubectl patch deployment api -n app --type=merge -p '{"value":"*x*"}'
```
"""


async def test_detail_shows_metadata_and_rendered_markdown(client, sessionmaker):
    report = await add(sessionmaker, title="Pod em OOMKilled", markdown=FULL_REPORT, uids=("u1", "u2"), attempts=2)

    response = await client.get(f"/reports/{report.id}")

    assert response.status_code == 200
    html = response.text
    assert "Pod em OOMKilled" in html
    assert 'class="badge badge-complete">COMPLETO</span>' in html
    assert "sev-alto" in html
    assert "18/10/2026 12:00 UTC" in html
    assert str(report.id) in html
    assert "<dt>Tentativas de análise</dt>\n    <dd>2</dd>" in html
    assert "<dt>Eventos</dt>\n    <dd>2</dd>" in html
    assert "<h3>Causa Raiz</h3>" in html
    assert "<li>container reiniciado 12 vezes</li>" in html
    assert "<table>" in html and "<td>64Mi</td>" in html
    assert 'href="/reports"' in html


async def test_detail_keeps_the_suggested_command_verbatim(client, sessionmaker):
    report = await add(sessionmaker, markdown=FULL_REPORT)

    html = (await client.get(f"/reports/{report.id}")).text

    assert "<pre><code" in html
    assert "*x*" in html and "<em>x</em>" not in html


async def test_detail_sanitizes_hostile_markdown(client, sessionmaker):
    hostile = ("## Problema 1: x\n\n- log: <script>alert(1)</script>\n- <img src=x onerror=alert(2)>\n"
               "- [clique](javascript:alert(3))\n- [ok](https://example.com)\n")
    report = await add(sessionmaker, markdown=hostile, title="x")

    html = (await client.get(f"/reports/{report.id}")).text

    article = html.split('<article class="report-content">')[1].split("</article>")[0]
    assert "<script" not in article and "onerror" not in article and "javascript:" not in article
    assert 'href="https://example.com"' in article


async def test_detail_escapes_hostile_title(client, sessionmaker):
    report = await add(sessionmaker, title="<script>alert(9)</script>", markdown="ok")

    html = (await client.get(f"/reports/{report.id}")).text

    assert "<script>alert(9)</script>" not in html
    assert "&lt;script&gt;" in html


async def test_detail_of_report_in_analysis_without_markdown(client, sessionmaker):
    report = await add(sessionmaker, status=ReportStatus.EM_ANALISE, title=None, severity=None)

    response = await client.get(f"/reports/{report.id}")

    assert response.status_code == 200
    assert "A análise está em andamento" in response.text
    assert "report-content\">" not in response.text


@pytest.mark.parametrize("status", [ReportStatus.INCOMPLETO, ReportStatus.COMPLETO])
async def test_detail_without_markdown_says_there_is_no_content(client, sessionmaker, status):
    report = await add(sessionmaker, status=status, markdown="   \n", title=None)

    html = (await client.get(f"/reports/{report.id}")).text

    assert "Este relatório não tem conteúdo de análise." in html
    assert "em andamento" not in html


async def test_detail_shows_partial_markdown_of_incomplete_report(client, sessionmaker):
    report = await add(sessionmaker, status=ReportStatus.INCOMPLETO, markdown="Analise parcial **sem formato**", title=None)

    html = (await client.get(f"/reports/{report.id}")).text

    assert "<strong>sem formato</strong>" in html


@pytest.mark.parametrize("report_id", [str(uuid.uuid4()), "nao-e-um-uuid", "123", "00000000-0000-0000-0000-00000000000g"])
async def test_detail_of_missing_or_malformed_id_is_404_page(client, report_id):
    response = await client.get(f"/reports/{report_id}")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    assert "Relatório não encontrado" in response.text


async def test_detail_has_no_form_or_button(client, sessionmaker):
    report = await add(sessionmaker, status=ReportStatus.COMPLETO, markdown=FULL_REPORT)

    html = (await client.get(f"/reports/{report.id}")).text

    assert "<form" not in html and "<button" not in html


def header_nav(html: str) -> str:
    return html.split("<nav>")[1].split("</nav>")[0]


async def test_reports_link_is_in_the_header_of_every_page(client, sessionmaker):
    report = await add(sessionmaker, markdown="ok")

    pages = {
        "home": await client.get("/"),
        "list": await client.get("/reports"),
        "detail": await client.get(f"/reports/{report.id}"),
        "not_found": await client.get(f"/reports/{uuid.uuid4()}"),
    }

    assert pages["not_found"].status_code == 404
    for name, response in pages.items():
        assert '<a href="/reports">Relatórios</a>' in header_nav(response.text), name


async def test_error_page_links_back_to_the_reports_list(client):
    html = (await client.get("/reports/nao-e-uuid")).text

    assert 'href="/reports" class="btn btn-primary"' in html
    assert "Voltar para tasks" not in html


MESSAGE_503 = "Banco de dados indisponível, tente novamente em instantes"


class BrokenSessionmaker:
    """sessionmaker cuja conexao com o banco falha com `error`."""

    def __init__(self, error):
        self.error = error

    def __call__(self):
        raise self.error


class FailingQuerySessionmaker:
    """Abre a sessao, mas a consulta falha."""

    def __init__(self, error):
        self.error = error

    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, *args, **kwargs):
        raise self.error

    async def get(self, *args, **kwargs):
        raise self.error


def database_failures():
    from sqlalchemy.exc import OperationalError

    return [
        BrokenSessionmaker(ConnectionRefusedError(111, "Connect call failed ('127.0.0.1', 5432)")),
        BrokenSessionmaker(TimeoutError("timeout ao conectar")),
        BrokenSessionmaker(OperationalError("SELECT secret_table", {}, Exception("senha=segredo"))),
        FailingQuerySessionmaker(OperationalError("SELECT secret_table", {}, Exception("senha=segredo"))),
    ]


@pytest.mark.parametrize("failing", range(4))
@pytest.mark.parametrize("path", ["/reports", f"/reports/{uuid.uuid4()}"])
async def test_database_failure_is_503_with_friendly_message(client, path, failing):
    main.app.state.sessionmaker = database_failures()[failing]

    response = await client.get(path)

    assert response.status_code == 503
    assert MESSAGE_503 in response.text
    for leak in ("senha", "secret_table", "Traceback", "ConnectionRefused", "OperationalError", "5432"):
        assert leak not in response.text
    assert '<a href="/reports">Relatórios</a>' in header_nav(response.text)


async def test_unrelated_errors_are_not_reported_as_database_unavailable(client):
    main.app.state.sessionmaker = BrokenSessionmaker(FileNotFoundError("template"))

    response = await client.get("/reports")

    assert response.status_code == 500 and MESSAGE_503 not in response.text


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("path", ["/reports", f"/reports/{uuid.uuid4()}"])
async def test_methods_that_change_data_are_not_allowed(client, method, path):
    response = await client.request(method, path)

    assert response.status_code == 405
