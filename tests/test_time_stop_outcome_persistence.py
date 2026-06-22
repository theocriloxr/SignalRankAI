from contextlib import asynccontextmanager

import pytest

import engine.realtime_outcome_tracker as rt


def test_parse_tp_levels_supports_dict_entries():
    tp_levels = rt._parse_tp_levels(
        [
            {"price": 101.25, "exit_percent": 33},
            {"tp": "102.5", "exit_percent": 33},
            {"target": 103.75, "exit_percent": 34},
        ]
    )

    assert tp_levels == [101.25, 102.5, 103.75]


@pytest.mark.asyncio
async def test_persist_outcome_maps_time_stop_channels(monkeypatch):
    captured = {}

    class _DummyOutcome:
        id = 123

    class _DummySession:
        async def execute(self, _stmt):
            return None

        async def commit(self):
            return None

    @asynccontextmanager
    async def _fake_get_session():
        yield _DummySession()

    async def _fake_upsert_outcome(session, signal_id, status, **kwargs):
        captured["signal_id"] = signal_id
        captured["status"] = status
        captured["kwargs"] = kwargs
        return _DummyOutcome()

    async def _fake_queue_outcome_notifications_for_outcome(session, outcome_id, signal_id, status):
        captured["queue"] = (outcome_id, signal_id, status)
        return 1

    monkeypatch.setattr("db.session.get_session", _fake_get_session)
    monkeypatch.setattr("db.pg_features.upsert_outcome", _fake_upsert_outcome)
    monkeypatch.setattr("db.pg_features.queue_outcome_notifications_for_outcome", _fake_queue_outcome_notifications_for_outcome)

    await rt._persist_outcome("sig-time-stop", "time_stop", 100.0, 100.0)

    assert captured["status"] == "time_stop"
    assert captured["kwargs"]["canonical_outcome"] == "time_stop"
    assert captured["kwargs"]["vip_fill_outcome"] == "pending"
    assert captured["kwargs"]["sentiment_outcome"] == "pending"
