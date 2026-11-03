"""Shadow labels follow the published plan (owner approval, 3 Nov 2026).

The tracker used to check only the final target, so a setup that reached TP1
and then fell back was labelled ``sl``. The setup-evidence filter measures
TP1-or-better against the plan's break-even (57-67 %), and saw only
TP3-before-SL rates (20-45 %), so it blocked every signal.
"""
from datetime import timedelta

import pytest

from engine.expectancy_shadow import realized_r
from engine.shadow_outcome_worker import ShadowOutcomeWorker
from services.segment_evidence import WIN_SHADOW
from utils.timeutils import now_utc_naive

STEP = timedelta(minutes=15)


def _row(direction="long", entry=100.0, stop=90.0, tps=(110.0, 120.0, 130.0)):
    created = now_utc_naive() - timedelta(hours=3)
    return {"id": 1, "signal_id": None, "asset": "BTCUSDT", "timeframe": "15m", "direction": direction,
            "entry": entry, "stop_loss": stop, "take_profit": list(tps), "ml_probability": 0.4,
            "rejection_reason": "ml_filter", "features": {}, "created_at": created}


def _path(row, bars):
    """bars: list of (low, high) after the rejection."""
    start = row["created_at"] + timedelta(minutes=1)
    return [{"timestamp": (start + STEP * i).isoformat(), "open": 100, "high": h, "low": l, "close": 100}
            for i, (l, h) in enumerate(bars)]


async def _label(monkeypatch, row, bars):
    candles = _path(row, bars)

    async def fake_candles(_asset, _tf):
        return candles

    async def fake_live(_asset):
        return None

    monkeypatch.setattr("data.fetcher.async_get_candles", fake_candles)
    monkeypatch.setattr("engine.realtime_outcome_tracker._get_live_price", fake_live)
    result = await ShadowOutcomeWorker()._evaluate_rows([row])
    return result[0][1] if result else None


@pytest.mark.asyncio
async def test_tp1_then_back_to_entry_is_tp1_not_sl(monkeypatch):
    # TP1 (110) touched, then price falls through entry and on to the original stop.
    assert await _label(monkeypatch, _row(), [(98, 111), (99, 105), (85, 101)]) == "tp1"


@pytest.mark.asyncio
async def test_tp2_then_back_to_entry_is_tp2(monkeypatch):
    assert await _label(monkeypatch, _row(), [(98, 112), (105, 121), (99.5, 115)]) == "tp2"


@pytest.mark.asyncio
async def test_final_target_is_tp3(monkeypatch):
    assert await _label(monkeypatch, _row(), [(98, 112), (105, 125), (118, 131)]) == "tp3"


@pytest.mark.asyncio
async def test_stop_before_any_target_is_sl(monkeypatch):
    assert await _label(monkeypatch, _row(), [(95, 105), (89, 104)]) == "sl"


@pytest.mark.asyncio
async def test_stop_and_first_target_in_one_bar_is_ambiguous(monkeypatch):
    assert await _label(monkeypatch, _row(), [(89, 111)]) == "ambiguous"


@pytest.mark.asyncio
async def test_open_after_tp1_waits(monkeypatch):
    assert await _label(monkeypatch, _row(), [(98, 111), (101, 115)]) is None


@pytest.mark.asyncio
async def test_short_mirror(monkeypatch):
    row = _row("short", 100.0, 110.0, (90.0, 80.0, 70.0))
    assert await _label(monkeypatch, row, [(89, 102), (95, 101)]) == "tp1"
    assert await _label(monkeypatch, row, [(95, 111)]) == "sl"


@pytest.mark.asyncio
async def test_two_targets_final_is_tp3(monkeypatch):
    row = _row(tps=(110.0, 120.0))
    assert await _label(monkeypatch, row, [(98, 111), (101, 121)]) == "tp3"
    assert await _label(monkeypatch, row, [(98, 111), (99, 105)]) == "tp1"


def test_tp1_tp2_count_for_the_evidence_filter_and_are_valued_by_the_plan():
    assert {"tp1", "tp2", "tp3"} <= set(WIN_SHADOW)
    # 50 % closed at TP1 (1R), remainder protected at entry.
    assert realized_r("long", 100, 90, [110, 120, 130], "tp1") == pytest.approx(0.5)
    assert realized_r("long", 100, 90, [110, 120, 130], "tp2") == pytest.approx(0.5 + 0.25 * 2)
    assert realized_r("long", 100, 90, [110, 120, 130], "tp3") == pytest.approx(3.0)
