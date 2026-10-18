import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _event_timestamp(event: dict) -> datetime | None:
    series = event.get("series") or {}
    for value in (
        series.get("lastObservedTime"),
        event.get("eventTime"),
        event.get("deprecatedLastTimestamp"),
    ):
        parsed = _parse(value)
        if parsed is not None:
            return parsed
    return None


def to_contract(event: dict) -> dict | None:
    """Converte um evento events.k8s.io/v1 (JSON da API) para o contrato de saida.

    Retorna None (com warning) quando o evento nao possui nenhum timestamp.
    """
    metadata = event.get("metadata") or {}
    uid = metadata.get("uid", "")
    try:
        timestamp = _event_timestamp(event)
    except ValueError:
        logger.warning("Evento %s descartado: timestamp invalido", uid)
        return None
    if timestamp is None:
        logger.warning(
            "Evento %s descartado: sem series.lastObservedTime, eventTime nem deprecatedLastTimestamp", uid
        )
        return None

    regarding = event.get("regarding") or {}
    return {
        "uid": uid,
        "type": event.get("type", ""),
        "reason": event.get("reason", ""),
        "message": event.get("note", ""),
        "namespace": metadata.get("namespace") or "",
        "involved_object": {
            "kind": regarding.get("kind", ""),
            "name": regarding.get("name", ""),
            "namespace": regarding.get("namespace") or "",
        },
        "timestamp": timestamp.isoformat(),
    }
