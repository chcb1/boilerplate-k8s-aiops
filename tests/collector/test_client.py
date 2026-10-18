import json
from types import SimpleNamespace

from tests.collector.test_transform import T1, make_event

from my_agent_app.collector.client import PAGE_SIZE, list_warning_events


class FakeApi:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def list_event_for_all_namespaces(self, **kwargs):
        self.calls.append(kwargs)
        items, token = self.pages[len(self.calls) - 1]
        metadata = {"continue": token} if token else {}
        return SimpleNamespace(data=json.dumps({"items": items, "metadata": metadata}))


def test_selects_warning_and_paginates_without_time_filter():
    e1, e2, e3 = (make_event(eventTime=T1) for _ in range(3))
    api = FakeApi([([e1, e2], "tok"), ([e3], None)])

    events = list_warning_events(api)

    assert len(events) == 3
    assert [c["field_selector"] for c in api.calls] == ["type=Warning", "type=Warning"]
    assert [c["_continue"] for c in api.calls] == [None, "tok"]
    assert all(c["limit"] == PAGE_SIZE for c in api.calls)
    assert all(c["_preload_content"] is False for c in api.calls)
    assert all(
        set(c) == {"field_selector", "limit", "_continue", "_preload_content"} for c in api.calls
    )


def test_events_without_timestamp_are_skipped():
    api = FakeApi([([make_event(eventTime=T1), make_event()], None)])
    assert len(list_warning_events(api)) == 1


def test_legacy_event_with_null_event_time_is_collected():
    legacy = make_event(eventTime=None, deprecatedLastTimestamp="2026-10-18T10:00:00Z")
    assert len(list_warning_events(FakeApi([([legacy], None)]))) == 1
