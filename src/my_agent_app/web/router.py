import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from my_agent_app.models import Report, ReportStatus
from my_agent_app.web.markdown import render_markdown

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

REPORTS_LIST_LIMIT = 200

STATUS_BADGE_CLASSES = {
    ReportStatus.EM_ANALISE: "badge-processing",
    ReportStatus.COMPLETO: "badge-complete",
    ReportStatus.INCOMPLETO: "badge-incomplete",
    ReportStatus.CORRIGINDO: "badge-executing",
    ReportStatus.CORRIGIDO: "badge-executed",
    ReportStatus.FALHA_CORRECAO: "badge-execution-failed",
}


def format_datetime(value) -> str:
    return value.strftime("%d/%m/%Y %H:%M UTC") if value else ""


templates.env.filters["datetime"] = format_datetime


def status_badge_class(status: str) -> str:
    return STATUS_BADGE_CLASSES.get(status, "badge-incomplete")


def display_title(title: str | None, status: str, report_id) -> str:
    """Titulo exibido; relatorios sem problema identificavel nao tem titulo proprio."""
    if title:
        return title
    if status == ReportStatus.EM_ANALISE:
        return "Análise em andamento"
    if status == ReportStatus.INCOMPLETO:
        return f"Análise incompleta ({str(report_id)[:8]})"
    return f"Relatório {str(report_id)[:8]}"


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "home.html")


@router.get("/reports", response_class=HTMLResponse)
async def list_reports(request: Request):
    # so as colunas exibidas: o Markdown de cada relatorio nao e carregado na listagem
    stmt = (
        select(
            Report.id,
            Report.title,
            Report.severity,
            Report.status,
            Report.created_at,
            func.cardinality(Report.event_uids).label("event_count"),
        )
        .order_by(Report.created_at.desc(), Report.id.desc())
        .limit(REPORTS_LIST_LIMIT + 1)  # a linha extra so indica que ha relatorios omitidos
    )
    async with request.app.state.sessionmaker() as session:
        rows = (await session.execute(stmt)).all()

    items = [
        {
            "id": row.id,
            "short_id": str(row.id)[:8],
            "title": display_title(row.title, row.status, row.id),
            "severity": row.severity,
            "status": row.status,
            "badge_class": status_badge_class(row.status),
            "created_at": row.created_at,
            "event_count": row.event_count,
        }
        for row in rows[:REPORTS_LIST_LIMIT]
    ]
    return templates.TemplateResponse(
        request,
        "reports.html",
        {"reports": items, "truncated": len(rows) > REPORTS_LIST_LIMIT, "limit": REPORTS_LIST_LIMIT},
    )


def report_not_found(request: Request):
    return templates.TemplateResponse(
        request,
        "error.html",
        {"status_code": 404, "title": "Não encontrado", "message": "Relatório não encontrado."},
        status_code=404,
    )


@router.get("/reports/{report_id}", response_class=HTMLResponse)
async def report_detail(request: Request, report_id: str):
    # str em vez de uuid.UUID: um ID malformado deve cair na pagina 404, e nao no 422 em JSON
    try:
        parsed_id = uuid.UUID(report_id)
    except ValueError:
        return report_not_found(request)

    async with request.app.state.sessionmaker() as session:
        report = await session.get(Report, parsed_id)
    if report is None:
        return report_not_found(request)

    has_content = bool(report.markdown and report.markdown.strip())
    return templates.TemplateResponse(
        request,
        "report_detail.html",
        {
            "report": report,
            "title": display_title(report.title, report.status, report.id),
            "badge_class": status_badge_class(report.status),
            "event_count": len(report.event_uids),
            "content": render_markdown(report.markdown) if has_content else None,
            "in_progress": report.status == ReportStatus.EM_ANALISE,
        },
    )


# conexao recusada com asyncpg levanta ConnectionRefusedError (ConnectionError), nao SQLAlchemyError
DATABASE_ERRORS = (SQLAlchemyError, ConnectionError, TimeoutError)


async def database_unavailable(request: Request, exc: Exception):
    logger.error("Banco indisponivel ao atender %s %s", request.method, request.url.path, exc_info=exc)
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": 503,
            "title": "Indisponível",
            "message": "Banco de dados indisponível, tente novamente em instantes",
        },
        status_code=503,
    )
