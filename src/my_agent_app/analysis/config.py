import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_STALE_TIMEOUT_MINUTES = 30


def positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value <= 0:
        logger.warning("%s invalido (%r); usando o padrao %d", name, raw, default)
        return default
    return value


def get_max_attempts() -> int:
    return positive_int("ANALYSIS_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS)


def get_stale_timeout_minutes() -> int:
    return positive_int("ANALYSIS_STALE_TIMEOUT_MINUTES", DEFAULT_STALE_TIMEOUT_MINUTES)
