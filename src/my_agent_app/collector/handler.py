import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class EventHandler:
    """Placeholder do PRD 002: exibe os eventos coletados no stdout."""

    async def handle(self, events: list[dict]) -> None:
        try:
            now = datetime.now(timezone.utc).isoformat()
            print(f"[{now}] lote: {len(events)} evento(s) Warning", flush=True)
            for event in events:
                print(json.dumps(event, ensure_ascii=False), flush=True)
        except Exception:
            logger.exception("Falha ao processar o lote de eventos")
