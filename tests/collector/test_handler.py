import json

from my_agent_app.collector.handler import EventHandler

EVENTS = [
    {"uid": "u1", "type": "Warning", "reason": "BackOff", "message": "m", "namespace": "default",
     "involved_object": {"kind": "Pod", "name": "p", "namespace": "default"}, "timestamp": "2026-10-18T10:00:00+00:00"},
    {"uid": "u2", "type": "Warning", "reason": "Failed", "message": "ação falhou", "namespace": "default",
     "involved_object": {"kind": "Pod", "name": "q", "namespace": "default"}, "timestamp": "2026-10-18T10:01:00+00:00"},
]


async def test_prints_header_and_one_json_per_event(capsys):
    await EventHandler().handle(EVENTS)

    lines = capsys.readouterr().out.strip().splitlines()
    assert "2 evento(s)" in lines[0]
    assert [json.loads(line) for line in lines[1:]] == EVENTS


async def test_stdout_independent_of_logging(capsys):
    import logging

    logging.disable(logging.CRITICAL)
    try:
        await EventHandler().handle(EVENTS)
    finally:
        logging.disable(logging.NOTSET)
    assert len(capsys.readouterr().out.strip().splitlines()) == 3


async def test_handle_swallows_errors():
    class Exploding(list):
        def __iter__(self):
            raise RuntimeError("falha ao iterar")

    await EventHandler().handle(Exploding([{"uid": "u"}]))  # nao deve propagar
