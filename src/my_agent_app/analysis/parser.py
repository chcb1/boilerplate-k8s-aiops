import logging
import re
import unicodedata
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

SEVERITIES = ("CRITICO", "ALTO", "MEDIO", "BAIXO")
MAX_TITLE_LENGTH = 255  # tamanho da coluna reports.title

_PROBLEM_HEADING = re.compile(r"^##[ \t]+Problema[ \t]+\d+[ \t]*:?[ \t]*(?P<title>.*)$", re.IGNORECASE | re.MULTILINE)
_SEVERITY = re.compile(r"\*\*Severidade:?\*\*:?[ \t]*(?P<value>[^\n]*)", re.IGNORECASE)
_EVENTS = re.compile(r"\*\*Eventos:?\*\*:?[ \t]*(?P<value>[^\n]*(?:\n(?![ \t]*(?:\n|#|-[ \t]+\*\*))[^\n]*)*)", re.IGNORECASE)
_ROOT_CAUSE = re.compile(r"^#{2,4}[ \t]+Causa Raiz[ \t]*\n(?P<body>.*?)(?=^#{1,4}[ \t]|\Z)", re.IGNORECASE | re.MULTILINE | re.DOTALL)
_UID_TOKEN = re.compile(r"[0-9A-Za-z][0-9A-Za-z._-]*")


@dataclass
class Problem:
    title: str
    markdown: str
    severity: str | None
    event_uids: list[str]
    inconclusive: bool


@dataclass
class ParseResult:
    problems: list[Problem] = field(default_factory=list)
    unreferenced: list[str] = field(default_factory=list)


def _fold(text: str) -> str:
    """Remove acentos e passa para maiusculas, para tolerar 'CRÍTICO' e 'Médio'."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().upper()


def _severity(section: str, title: str) -> str | None:
    match = _SEVERITY.search(section)
    first = _fold(match["value"]).strip(" *_`").split() if match else []
    value = first[0].strip("|,.:;") if first else ""
    if value in SEVERITIES:
        return value
    logger.warning("Problema %r sem severidade reconhecivel (%r); severity ficara vazia", title, match and match["value"])
    return None


def _inconclusive(section: str) -> bool:
    match = _ROOT_CAUSE.search(section)
    if not match:
        return False
    lines = [line.strip(" \t*_`>-") for line in match["body"].splitlines() if line.strip()]
    return bool(lines) and _fold(lines[0]).startswith("INCONCLUSIV")


def _mentioned_uids(section: str) -> list[str]:
    match = _EVENTS.search(section)
    return _UID_TOKEN.findall(match["value"]) if match else []


def parse_report(response: str, batch_uids: list[str]) -> ParseResult:
    """Converte a resposta Markdown do agente em problemas com os UIDs do lote que cada um cobre."""
    headings = list(_PROBLEM_HEADING.finditer(response or ""))
    known = set(batch_uids)
    assigned: set[str] = set()
    problems: list[Problem] = []

    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(response)
        section = response[heading.start():end].strip().removesuffix("---").rstrip()
        title = (heading["title"].strip() or f"Problema {index + 1}")[:MAX_TITLE_LENGTH].rstrip()

        uids: list[str] = []
        for token in _mentioned_uids(section):
            if token not in known:
                logger.warning("Problema %r cita UID %r que nao pertence ao lote; ignorado", title, token)
            elif token in assigned:
                logger.warning("UID %r citado em mais de um problema; mantido no primeiro", token)
            elif token not in uids:
                uids.append(token)
        if not uids:
            logger.warning("Problema %r sem nenhum UID valido do lote; descartado", title)
            continue

        assigned.update(uids)
        problems.append(Problem(title, section, _severity(section, title), uids, _inconclusive(section)))

    unreferenced = [uid for uid in batch_uids if uid not in assigned]
    if problems and unreferenced:
        logger.warning("%d evento(s) do lote nao foram referenciados por nenhum problema: %s", len(unreferenced), unreferenced)
    return ParseResult(problems, unreferenced)
