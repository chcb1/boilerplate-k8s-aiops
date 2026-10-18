import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_MINUTES = 3


def get_interval_minutes() -> int:
    raw = os.environ.get("EVENT_COLLECTION_INTERVAL_MINUTES")
    if raw is None or raw.strip() == "":
        return DEFAULT_INTERVAL_MINUTES
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value <= 0:
        logger.warning(
            "EVENT_COLLECTION_INTERVAL_MINUTES invalido (%r); usando o padrao de %d minutos",
            raw,
            DEFAULT_INTERVAL_MINUTES,
        )
        return DEFAULT_INTERVAL_MINUTES
    return value
