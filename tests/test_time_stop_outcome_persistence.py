from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

import engine.realtime_outcome_tracker as rt


def _read_result(statement, lifecycle_state="TP1_HIT"):
    from db.models import Signal, SignalTrackingEvent, SignalLifecycle
    descriptions = getattr(statement, "column_descriptions", [])
    entity = descriptions[0].get("entity") if descriptions else None
    value = None
    if entity is Signal:
        value = SimpleNamespace(direction="long", entry=100, stop_loss=95, take_profit=[102, 104, 106],
                                asset="BTCUSDT", timeframe="1h", ml_probability=None, created_at=None)
    elif entity is SignalTrackingEvent:
        value = 102.0
    elif entity is SignalLifecycle:
        value = SimpleNamespace(state=lifecycle_state, highest_tp_hit=1 if lifecycle_state == "TP1_HIT" else 0)
    return SimpleNamespace(scalar_one_or_none=lambda: value, all=lambda: [])


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
            return _read_result(_stmt, lifecycle_state="CLOSED_TIME_STOP")

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


@pytest.mark.asyncio
async def test_persist_outcome_counts_tp1_as_partial_win(monkeypatch):
    captured = {}

    class _DummyOutcome:
        id = 124

    class _DummySession:
        async def execute(self, _stmt):
            return _read_result(_stmt)

        async def commit(self):
            return None

    @asynccontextmanager
    async def _fake_get_session():
        yield _DummySession()

    async def _fake_upsert_outcome(session, signal_id, status, **kwargs):
        captured.update(status=status, kwargs=kwargs)
        return _DummyOutcome()

    async def _fake_queue(*_args, **_kwargs):
        return 1

    monkeypatch.setattr("db.session.get_session", _fake_get_session)
    monkeypatch.setattr("db.pg_features.upsert_outcome", _fake_upsert_outcome)
    monkeypatch.setattr("db.pg_features.queue_outcome_notifications_for_outcome", _fake_queue)

    await rt._persist_outcome("sig-tp1", "tp1", 100.0, 102.0)

    assert captured["status"] == "tp1"
    assert captured["kwargs"]["canonical_outcome"] == "partial_win"
    assert captured["kwargs"]["meta"]["tp1_hit"] is True
    assert captured["kwargs"]["meta"]["tp_hit_index"] == 1
