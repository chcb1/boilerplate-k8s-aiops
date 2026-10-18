import asyncio
import json
import logging

from kubernetes import client, config

from my_agent_app.collector.transform import to_contract

logger = logging.getLogger(__name__)

PAGE_SIZE = 500
WARNING_SELECTOR = "type=Warning"


def load_cluster_config() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


def list_warning_events(api: client.EventsV1Api) -> list[dict]:
    """Lista todos os Warnings de todos os namespaces, paginando, sem filtro temporal.

    Le o JSON cru (`_preload_content=False`): o modelo pydantic do SDK rejeita
    `eventTime: null`, que e como a API serve os eventos de controllers legados.
    """
    events: list[dict] = []
    token = None
    while True:
        response = api.list_event_for_all_namespaces(
            field_selector=WARNING_SELECTOR,
            limit=PAGE_SIZE,
            _continue=token,
            _preload_content=False,
        )
        body = json.loads(response.data)
        for item in body.get("items", []):
            converted = to_contract(item)
            if converted is not None:
                events.append(converted)
        token = (body.get("metadata") or {}).get("continue")
        if not token:
            return events


class ClusterEvents:
    """Fonte de eventos Warning do cluster; configura o SDK de forma preguicosa."""

    def __init__(self) -> None:
        self._api: client.EventsV1Api | None = None

    def _get_api(self) -> client.EventsV1Api:
        if self._api is None:
            load_cluster_config()
            self._api = client.EventsV1Api()
        return self._api

    def _fetch(self) -> list[dict]:
        return list_warning_events(self._get_api())

    async def fetch(self) -> list[dict]:
        return await asyncio.to_thread(self._fetch)
