"""Shadow outcomes must not be judged from a candle window that starts after the rejection (2 Nov 2026).

Providers return a fixed number of recent bars (200 by default, under 17 hours
of 5m bars). Production's ML tracker ran about 35 hours behind on 2 Nov, so 5m
rows were being labelled from candles that began long after the rejection.
"""
from datetime import timedelta

import pytest

from engine import shadow_outcome_worker as sow
from engine.shadow_outcome_worker import UNVERIFIABLE_OUTCOME, ShadowOutcomeWorker
from utils.timeutils import now_utc_naive


def _row(created_at, timeframe="5m"):
    return {"id": 1, "signal_id": None, "asset": "BTCUSDT", "timeframe": timeframe, "direction": "long",
            "entry": 100.0, "stop_loss": 90.0, "take_profit": [110.0, 120.0, 130.0], "ml_probability": 0.4,
            "rejection_reason": "ml_filter", "features": {}, "created_at": created_at}


def _candles(start, count, step, low=95.0, high=105.0, hit_at=None, hit=("low", 80.0)):
    out = []
    for i in range(count):
        candle = {"timestamp": (start + step * i).isoformat(), "open": 100, "high": high, "low": low, "close": 100}
        if hit_at is not None and i == hit_at:
            candle[hit[0]] = hit[1]
        out.append(candle)
    return out


def _patch(monkeypatch, candles, live_price=None):
    calls = {"live": 0}

    async def fake_candles(_asset, _tf):
        return candles

    async def fake_live(_asset):
        calls["live"] += 1
        return live_price

    monkeypatch.setattr("data.fetcher.async_get_candles", fake_candles)
    monkeypatch.setattr("engine.realtime_outcome_tracker._get_live_price", fake_live)
    return calls


@pytest.mark.asyncio
async def test_window_starting_after_the_rejection_is_unverifiable(monkeypatch):
    created = now_utc_naive() - timedelta(hours=35)
    # 200 bars of 5m ending now: they start about 18 hours after the rejection,
    # and a target touch inside them must not become a win.
    step = timedelta(minutes=5)
    candles = _candles(now_utc_naive() - step * 200, 200, step, hit_at=50, hit=("high", 140.0))
    calls = _patch(monkeypatch, candles, live_price=135.0)
    result = await ShadowOutcomeWorker()._evaluate_rows([_row(created)])
    assert [outcome for _, outcome in result] == [UNVERIFIABLE_OUTCOME]
    assert calls["live"] == 0


@pytest.mark.asyncio
async def test_window_covering_the_rejection_is_still_judged(monkeypatch):
    created = now_utc_naive() - timedelta(hours=2)
    step = timedelta(minutes=5)
    candles = _candles(created - step * 10, 40, step, hit_at=20, hit=("low", 85.0))
    _patch(monkeypatch, candles)
    result = await ShadowOutcomeWorker()._evaluate_rows([_row(created)])
    assert [outcome for _, outcome in result] == ["sl"]


@pytest.mark.asyncio
async def test_first_bar_after_the_rejection_counts_as_covered(monkeypatch):
    created = now_utc_naive() - timedelta(hours=2)
    step = timedelta(minutes=5)
    # The window starts with the bar right after the one containing the
    # rejection; that bar is skipped anyway, so nothing is missing.
    candles = _candles(created + timedelta(minutes=3), 20, step, hit_at=0, hit=("high", 140.0))
    _patch(monkeypatch, candles)
    result = await ShadowOutcomeWorker()._evaluate_rows([_row(created)])
    assert [outcome for _, outcome in result] == ["tp3"]


@pytest.mark.asyncio
async def test_old_row_without_candles_is_not_decided_by_live_price(monkeypatch):
    calls = _patch(monkeypatch, [], live_price=80.0)
    result = await ShadowOutcomeWorker()._evaluate_rows([_row(now_utc_naive() - timedelta(hours=6))])
    assert result == []
    assert calls["live"] == 0


@pytest.mark.asyncio
async def test_recent_row_without_candles_may_use_live_price(monkeypatch):
    calls = _patch(monkeypatch, [], live_price=80.0)
    result = await ShadowOutcomeWorker()._evaluate_rows([_row(now_utc_naive() - timedelta(minutes=8))])
    assert [outcome for _, outcome in result] == ["sl"]
    assert calls["live"] == 1


def test_unverifiable_is_excluded_from_learning_labels():
    from ml.train_model import _normalize_shadow_outcome
    from services.strategy_scorecard import outcome_r
    from engine.expectancy_shadow import realized_r

    assert _normalize_shadow_outcome(UNVERIFIABLE_OUTCOME) is None
    assert outcome_r("long", 100, 90, [110, 120, 130], UNVERIFIABLE_OUTCOME) is None
    assert realized_r("long", 100, 90, [110, 120, 130], UNVERIFIABLE_OUTCOME) is None
    assert sow._timeframe_seconds("4h") == 14400
