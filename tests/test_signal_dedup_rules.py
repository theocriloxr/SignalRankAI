from __future__ import annotations

from datetime import datetime

import pytest

from db.models import Signal
from db.pg_features import get_or_create_signal
from utils.async_runner import run_sync


class _FakeResult:
    def __init__(self, rows: list[Signal] | None = None):
        self._rows = list(rows or [])

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows: list[Signal] | None = None):
        self._rows = list(rows or [])
        self.added = []
        self.flushed = 0

    async def execute(self, _statement):
        return _FakeResult(self._rows)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1


def test_get_or_create_signal_blocks_when_asset_is_already_open(monkeypatch):
    existing = Signal(
        signal_id="sig-open-1",
        asset="SOLUSDT",
        timeframe="15m",
        direction="long",
        entry=82.34,
        stop_loss=81.2,
        take_profit='[83.5]',
        rr_estimate=1.5,
        score=77.0,
        regime="trend",
        strategy_name="breakout",
        strategy_group="momentum",
        strength=0.9,
        created_at=datetime.utcnow(),
        fingerprint="fp-open-1",
        expires_at=None,
        ml_probability=None,
        archived=False,
        expired=False,
        is_near_order_block=False,
    )

    session = _FakeSession([existing])

    monkeypatch.setattr(
        "core.redis_state.state.get_active_trades_sync",
        lambda: {
            "trade-1": {
                "signal_id": "sig-open-1",
                "signal": {"asset": "SOLUSDT", "symbol": "SOLUSDT"},
            }
        },
    )

    result = run_sync(
        get_or_create_signal(
            session,
            {
                "asset": "SOLUSDT",
                "timeframe": "15m",
                "direction": "long",
                "entry": 82.34,
                "stop_loss": 81.2,
                "take_profit": [83.5],
                "strategy_group": "momentum",
                "strategy_name": "breakout",
            },
        )
    )

    assert result.signal_id == "sig-open-1"
    assert session.added == []


def test_get_or_create_signal_reuses_nearby_entry_within_buffer(monkeypatch):
    existing = Signal(
        signal_id="sig-asset-1",
        asset="SOLUSDT",
        timeframe="15m",
        direction="long",
        entry=82.33,
        stop_loss=81.2,
        take_profit='[83.5]',
        rr_estimate=1.5,
        score=77.0,
        regime="trend",
        strategy_name="breakout",
        strategy_group="momentum",
        strength=0.9,
        created_at=datetime.utcnow(),
        fingerprint="fp-1",
        expires_at=None,
        ml_probability=None,
        archived=False,
        expired=False,
        is_near_order_block=False,
    )

    session = _FakeSession([existing])

    monkeypatch.setattr("core.redis_state.state.get_active_trades_sync", lambda: {})
    monkeypatch.setenv("SIGNAL_MIN_INTERVAL_HOURS", "0")
    monkeypatch.setenv("SIGNAL_PRICE_BUFFER_PCT", "0.5")

    result = run_sync(get_or_create_signal(
        session,
        {
            "asset": "SOLUSDT",
            "timeframe": "15m",
            "direction": "long",
            "entry": 82.34,
            "stop_loss": 81.2,
            "take_profit": [83.5],
            "strategy_group": "momentum",
            "strategy_name": "breakout",
        },
    ))

    assert result.signal_id == "sig-asset-1"
    assert session.added == []


def test_get_or_create_signal_clears_orphan_redis_active_trade(monkeypatch):
    session = _FakeSession([])
    removed: list[str] = []

    monkeypatch.setattr(
        "core.redis_state.state.get_active_trades_sync",
        lambda: {
            "missing-signal-id": {
                "signal_id": "missing-signal-id",
                "symbol": "SOLUSDT",
                "asset": "SOLUSDT",
                "updated_at": 1,
            }
        },
    )
    monkeypatch.setattr("core.redis_state.state.remove_active_trade_sync", lambda signal_id: removed.append(signal_id) or True)
    monkeypatch.setenv("SIGNAL_MIN_INTERVAL_HOURS", "0")

    result = run_sync(get_or_create_signal(
        session,
        {
            "asset": "SOLUSDT",
            "timeframe": "15m",
            "direction": "long",
            "entry": 82.34,
            "stop_loss": 81.2,
            "take_profit": [83.5],
            "score": 80,
            "confidence": 0.8,
            "strategy_group": "momentum",
            "strategy_name": "breakout",
        },
        dedup_hours=0,
    ))

    assert removed == ["missing-signal-id"]
    assert result in session.added
    assert result.asset == "SOLUSDT"
