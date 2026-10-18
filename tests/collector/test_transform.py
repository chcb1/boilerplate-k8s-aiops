import logging

from my_agent_app.collector.transform import to_contract

T1 = "2026-10-18T10:00:00.000000Z"
T2 = "2026-10-18T11:00:00.000000Z"
T3 = "2026-10-18T12:00:00.000000Z"


def make_event(**overrides) -> dict:
    event = {
        "metadata": {"name": "e1", "namespace": "default", "uid": "uid-1"},
        "type": "Warning",
        "reason": "BackOff",
        "note": "Back-off pulling image",
        "regarding": {"kind": "Pod", "name": "nginx-1", "namespace": "default"},
        "eventTime": None,
    }
    event.update(overrides)
    return event


def iso(value: str) -> str:
    return value.replace(".000000Z", "+00:00").replace("Z", "+00:00")


def test_series_wins_over_event_time():
    event = make_event(eventTime=T1, series={"count": 3, "lastObservedTime": T3})
    assert to_contract(event)["timestamp"] == iso(T3)


def test_event_time_without_series():
    assert to_contract(make_event(eventTime=T2))["timestamp"] == iso(T2)


def test_legacy_event_with_null_event_time_uses_deprecated_last_timestamp():
    event = make_event(eventTime=None, deprecatedLastTimestamp="2026-10-18T10:00:00Z")
    assert to_contract(event)["timestamp"] == "2026-10-18T10:00:00+00:00"


def test_no_timestamp_is_discarded_with_warning(caplog):
    with caplog.at_level(logging.WARNING):
        assert to_contract(make_event()) is None
    assert "uid-1" in caplog.text


def test_field_mapping_and_contract_keys():
    assert to_contract(make_event(eventTime=T1)) == {
        "uid": "uid-1",
        "type": "Warning",
        "reason": "BackOff",
        "message": "Back-off pulling image",
        "namespace": "default",
        "involved_object": {"kind": "Pod", "name": "nginx-1", "namespace": "default"},
        "timestamp": iso(T1),
    }


def test_cluster_scoped_involved_object_namespace_is_empty():
    event = make_event(eventTime=T1, regarding={"kind": "Node", "name": "kind-control-plane"})
    assert to_contract(event)["involved_object"]["namespace"] == ""
