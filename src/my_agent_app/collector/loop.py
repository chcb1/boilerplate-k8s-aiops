import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

from kubernetes.client.exceptions import ApiException

from my_agent_app.collector.config import get_interval_minutes

logger = logging.getLogger(__name__)

FetchEvents = Callable[[], Awaitable[list[dict]]]


class EventHandler(Protocol):
    async def handle(self, events: list[dict]) -> None: ...


class EventCollector:
    def __init__(
        self,
        fetch: FetchEvents,
        handler: EventHandler,
        interval_seconds: float | None = None,
    ) -> None:
        self._fetch = fetch
        self._handler = handler
        self._interval_seconds = (
            interval_seconds if interval_seconds is not None else get_interval_minutes() * 60
        )
        # referencias fortes: o loop de eventos so guarda referencia fraca das tasks
        self._dispatched: set[asyncio.Task] = set()

    async def run_cycle(self) -> None:
        try:
            events = await self._fetch()
        except ApiException as exc:
            if exc.status == 403:
                logger.error(
                    "Sem permissao para listar eventos (events.k8s.io): conceda get/list em "
                    "'events' de todos os namespaces (ClusterRole). Nova tentativa no proximo ciclo. %s",
                    exc.reason,
                )
            else:
                logger.error("Erro da API do Kubernetes ao coletar eventos (status %s): %s", exc.status, exc.reason)
            return
        except Exception:
            logger.exception("Falha ao coletar eventos do cluster; nova tentativa no proximo ciclo")
            return

        logger.info("Coleta concluida: %d evento(s) Warning", len(events))
        if not events:
            return
        task = asyncio.create_task(self._handler.handle(events))
        self._dispatched.add(task)
        task.add_done_callback(self._dispatched.discard)

    async def drain(self) -> None:
        """Aguarda os despachos em andamento (usado em testes e no shutdown)."""
        if self._dispatched:
            await asyncio.gather(*self._dispatched, return_exceptions=True)

    async def run(self) -> None:
        while True:
            await self.run_cycle()
            await asyncio.sleep(self._interval_seconds)
