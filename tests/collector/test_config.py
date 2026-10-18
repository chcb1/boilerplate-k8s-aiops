import logging

import pytest

from my_agent_app.collector.config import DEFAULT_INTERVAL_MINUTES, get_interval_minutes


def test_default_when_unset(monkeypatch):
    monkeypatch.delenv("EVENT_COLLECTION_INTERVAL_MINUTES", raising=False)
    assert get_interval_minutes() == DEFAULT_INTERVAL_MINUTES == 3


def test_valid_value(monkeypatch):
    monkeypatch.setenv("EVENT_COLLECTION_INTERVAL_MINUTES", "5")
    assert get_interval_minutes() == 5


@pytest.mark.parametrize("raw", ["abc", "0", "-2"])
def test_invalid_value_falls_back_and_warns(monkeypatch, caplog, raw):
    monkeypatch.setenv("EVENT_COLLECTION_INTERVAL_MINUTES", raw)
    with caplog.at_level(logging.WARNING):
        assert get_interval_minutes() == 3
    assert "EVENT_COLLECTION_INTERVAL_MINUTES" in caplog.text
