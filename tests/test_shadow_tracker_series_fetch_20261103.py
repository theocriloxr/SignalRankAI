"""The shadow tracker fetches each asset x timeframe once per batch (3 Nov 2026).

Production: 150-row batches took ~90 s because candles were fetched per row,
while the engine re-logs the same setup every scan (ML-layer rejections arrive
at ~165k/day). The tracker fell from ~40 h to ~60 h behind in a day, so most
5m/15m rows could only end as unverifiable.
"""
from datetime import timedelta

import pytest

from engine.shadow_outcome_worker import UNVERIFIABLE_OUTCOME, ShadowOutcomeWorker
from utils.timeutils import now_utc_naive


def _row(i, asset, timeframe, created_at):
    return {"id": i, "signal_id": None, "asset": asset, "timeframe": timeframe, "direction": "long",
            "entry": 100.0, "stop_loss": 90.0, "take_profit": [110.0, 120.0, 130.0], "ml_probability": 0.4,
            "rejection_reason": "ml_filter", "features": {}, "created_at": created_at}


def _candles(start, count, step, hit_at, hit):
    out = []
    for i in range(count):
        candle = {"timestamp": (start + step * i).isoformat(), "open": 100, "high": 105.0, "low": 95.0,
                  "close": 100}
        if i == hit_at:
            candle[hit[0]] = hit[1]
        out.append(candle)
    return out


@pytest.mark.asyncio
async def test_candles_are_fetched_once_per_series(monkeypatch):
    created = now_utc_naive() - timedelta(hours=2)
    step = timedelta(minutes=5)
    by_series = {
        ("BTCUSDT", "5m"): _candles(created - step * 5, 40, step, 20, ("low", 85.0)),
        ("ETHUSDT", "15m"): _candles(created - step * 5, 40, step, 10, ("high", 140.0)),
    }
    calls = []

    async def fake_candles(asset, tf):
        calls.append((asset, tf))
        return by_series[(asset, tf)]

    async def fake_live(_asset):
        raise AssertionError("candles decide these rows")

    monkeypatch.setattr("data.fetcher.async_get_candles", fake_candles)
    monkeypatch.setattr("engine.realtime_outcome_tracker._get_live_price", fake_live)
    rows = [_row(i, "BTCUSDT", "5m", created) for i in range(100)]
    rows += [_row(100 + i, "ETHUSDT", "15m", created) for i in range(50)]
    result = await ShadowOutcomeWorker()._evaluate_rows(rows)
    assert sorted(calls) == sorted(by_series)
    outcomes = {row["id"]: outcome for row, outcome in result}
    assert len(outcomes) == 150
    assert {outcomes[i] for i in range(100)} == {"sl"}
    assert {outcomes[i] for i in range(100, 150)} == {"tp3"}


@pytest.mark.asyncio
async def test_failed_series_fetch_still_lets_old_rows_wait(monkeypatch):
    old = now_utc_naive() - timedelta(hours=30)
    calls = []

    async def failing(asset, tf):
        calls.append((asset, tf))
        raise TimeoutError("provider")

    async def fake_live(_asset):
        raise AssertionError("a live price cannot judge a 30 h old 5m row")

    monkeypatch.setattr("data.fetcher.async_get_candles", failing)
    monkeypatch.setattr("engine.realtime_outcome_tracker._get_live_price", fake_live)
    result = await ShadowOutcomeWorker()._evaluate_rows([_row(i, "SOLUSDT", "5m", old) for i in range(5)])
    assert calls == [("SOLUSDT", "5m")]
    assert result == []


@pytest.mark.asyncio
async def test_window_past_the_rejection_is_unverifiable_for_every_row(monkeypatch):
    created = now_utc_naive() - timedelta(hours=35)
    step = timedelta(minutes=5)
    candles = _candles(now_utc_naive() - step * 200, 200, step, 50, ("high", 140.0))

    async def fake_candles(_asset, _tf):
        return candles

    monkeypatch.setattr("data.fetcher.async_get_candles", fake_candles)
    result = await ShadowOutcomeWorker()._evaluate_rows([_row(i, "BTCUSDT", "5m", created) for i in range(3)])
    assert [outcome for _, outcome in result] == [UNVERIFIABLE_OUTCOME] * 3
