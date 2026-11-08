"""Real TP2/TP3 ladders and entry tracking (owner report, 8 Nov 2026).

BTCUSDT 5m MACD Momentum (c790abba): entry 75,969.40, stop 75,857.77, one
target 76,284.19, so half the position had no target after TP1. The owner also
reported entries not being tracked: the tracker ignored the 1m candle the
signal was created in, so a long that dipped just after delivery and stayed
below entry stayed "waiting for entry" while the trade was running.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.signal_quality_gate import evaluate_signal_quality
from engine import realtime_outcome_tracker as tracker
from services.trade_profiles import apply_trade_profile_to_signal
from signalrank_telegram.tier_signal_formatter import format_vip_signal

BTC = {"asset": "BTCUSDT", "timeframe": "5m", "direction": "long", "entry": 75969.40, "stop_loss": 75857.77,
       "take_profit": [76284.19], "atr": 120, "strategy_name": "MACD Momentum", "score": 56.5,
       "signal_id": "c790abba-1a4", "suggested_position_size": 0.448}


def test_single_target_gets_tracked_tp2_and_tp3_in_one_r_steps():
    sig = apply_trade_profile_to_signal(dict(BTC))
    assert sig["take_profit"] == [76284.19, 76395.82, 76507.45]
    assert sig["take_profit_authored"] == [76284.19]
    assert sig["rr_ratio"] == 2.8199 and sig["rr_final"] == 2.8199 and sig["rr_ladder_final"] == 4.8199


def test_short_ladder_and_three_authored_targets_are_untouched():
    short = apply_trade_profile_to_signal(dict(BTC, direction="short", entry=100.0, stop_loss=101.0,
                                               take_profit=[98.5]))
    assert short["take_profit"] == [98.5, 97.5, 96.5]
    full = apply_trade_profile_to_signal(dict(BTC, take_profit=[76100.0, 76200.0, 76300.0]))
    assert full["take_profit"] == [76100.0, 76200.0, 76300.0] and "take_profit_authored" not in full


def test_ladder_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("SIGNAL_TARGET_LADDER_ENABLED", "false")
    assert apply_trade_profile_to_signal(dict(BTC))["take_profit"] == [76284.19]


def test_ladder_never_helps_a_setup_pass_the_quality_gate():
    base = dict(BTC, entry=100.0, stop_loss=99.0, take_profit=[101.2], score=80)
    laddered = apply_trade_profile_to_signal(dict(base))
    assert len(laddered["take_profit"]) == 3
    assert "final_rr_below_minimum" in evaluate_signal_quality(laddered).reasons


def test_card_shows_every_tracked_target_and_says_where_they_come_from():
    card = format_vip_signal(apply_trade_profile_to_signal(dict(BTC)))
    assert "TP2: 76,395.82" in card and "TP3: 76,507.45" in card
    assert "TP2 then stop at entry +2.36R" in card
    assert "no further target" not in card
    assert "TP2 and TP3 are 1R steps beyond it" in card


def _obs(price, high=None, low=None, start=None):
    return tracker.OutcomePriceObservation(asset="BTCUSDT", price=price, provider="test", quote_time=None,
                                           provider_trusted=True, high=high, low=low,
                                           range_time=start.isoformat() if start else None,
                                           range_trusted=start is not None)


def test_creation_candle_counts_for_the_entry_check_only():
    created = datetime(2026, 11, 8, 18, 34, 40, tzinfo=timezone.utc)
    signal = {"created_at": created.replace(tzinfo=None)}
    candle = created.replace(second=0)  # the 1m candle the signal was born in
    # Price dipped to 75,900 after delivery; the creation candle traded at entry.
    high, low = tracker._entry_touch_range(signal, _obs(75900.0, 75980.0, 75890.0, candle), None, None)
    assert (high, low) == (75980.0, 75890.0)
    # A candle from well before creation never counts.
    old = tracker._entry_touch_range(signal, _obs(75900.0, 75980.0, 75890.0, created - timedelta(minutes=5)),
                                     None, None)
    assert old == (None, None)
    # The strict range wins whenever it is available.
    assert tracker._entry_touch_range(signal, _obs(1.0), 2.0, 1.0) == (2.0, 1.0)


def test_entry_band_is_a_tenth_of_the_risk():
    assert tracker._within_entry_band(75969.40, 75857.77, 75960.0)       # 9.4 away, band 11.2
    assert not tracker._within_entry_band(75969.40, 75857.77, 75940.0)   # 29.4 away
