import asyncio
import logging

from kubernetes.client.exceptions import ApiException

from my_agent_app.collector.loop import EventCollector

EVENT = {"uid": "u1"}


class RecordingHandler:
    def __init__(self, delay=0.0):
        self.delay = delay
        self.batches = []

    async def handle(self, events):
        await asyncio.sleep(self.delay)
        self.batches.append(events)


async def test_first_cycle_runs_immediately_and_dispatches():
    handler = RecordingHandler()

    async def fetch():
        return [EVENT]

    collector = EventCollector(fetch, handler, interval_seconds=3600)
    task = asyncio.create_task(collector.run())
    await asyncio.sleep(0.05)
    task.cancel()

    assert handler.batches == [[EVENT]]


async def test_slow_handler_does_not_block_next_cycle():
    handler = RecordingHandler(delay=1.0)
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        return [EVENT]

    collector = EventCollector(fetch, handler, interval_seconds=0.05)
    task = asyncio.create_task(collector.run())
    await asyncio.sleep(0.3)
    task.cancel()

    assert calls >= 3
    assert handler.batches == []  # handlers ainda em andamento


async def test_empty_list_does_not_dispatch():
    handler = RecordingHandler()

    async def fetch():
        return []

    await EventCollector(fetch, handler, interval_seconds=1).run_cycle()
    await asyncio.sleep(0.01)
    assert handler.batches == []


async def test_rbac_error_logged_and_loop_continues(caplog):
    handler = RecordingHandler()
    outcomes = [ApiException(status=403, reason="Forbidden"), ConnectionError("down"), [EVENT]]

    async def fetch():
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    collector = EventCollector(fetch, handler, interval_seconds=0.02)
    with caplog.at_level(logging.ERROR):
        task = asyncio.create_task(collector.run())
        await asyncio.sleep(0.2)
        task.cancel()

    assert "get/list" in caplog.text and "events" in caplog.text
    assert "Falha ao coletar eventos" in caplog.text
    assert handler.batches == [[EVENT]]
