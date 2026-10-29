"""Realistic execution in the zone-rejection backtest (29 Oct 2026).

Every expected value below is worked out by hand from the default cost model:
taker 5 bps, maker 2 bps, spread 2 bps (1 bp paid per market fill), slippage
3 bps, so a market or stop fill is 4 bps worse than the quoted price.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bt_realism", ROOT / "scripts" / "backtest_zone_rejection.py")
bt = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bt
spec.loader.exec_module(bt)

MODEL = bt.CostModel()
LONG = {"direction": "LONG", "entry": 100.0, "stop_loss": 98.0, "take_profit": 104.0}
SHORT = {"direction": "SHORT", "entry": 100.0, "stop_loss": 102.0, "take_profit": 94.0}


def _bar(o, h, l, c):
    return {"timestamp": 0, "open": o, "high": h, "low": l, "close": c, "volume": 1.0}


def test_entry_is_the_next_open_and_a_stop_costs_more_than_1r():
    out = bt.simulate_execution(LONG, [_bar(100.0, 100.5, 97.5, 98.0)], MODEL, max_hold=10)
    # entry 100 x 1.0004 = 100.04; stop 98 x 0.9996 = 97.9608; fees 5 bps on both notionals
    assert out["exit"] == "stop" and out["bars"] == 1
    assert out["entry_fill"] == pytest.approx(100.04) and out["exit_fill"] == pytest.approx(97.9608)
    assert out["fees_r"] == pytest.approx((0.0005 * 100.04 + 0.0005 * 97.9608) / 2)
    assert out["r"] == pytest.approx((97.9608 - 100.04 - 0.0990004) / 2)  # -1.0891
    assert out["friction_r"] == pytest.approx(-1.0 - out["r"])


def test_a_gap_through_the_stop_fills_at_the_open():
    bars = [_bar(99.0, 99.5, 98.5, 98.6), _bar(96.0, 96.5, 95.5, 96.2)]
    out = bt.simulate_execution(LONG, bars, MODEL, max_hold=10)
    entry, exit_ = 99.0 * 1.0004, 96.0 * 0.9996
    assert out["exit"] == "stop" and out["bars"] == 2 and out["exit_fill"] == pytest.approx(exit_)
    assert out["r"] == pytest.approx((exit_ - entry - 0.0005 * (entry + exit_)) / 2)  # about -1.59R
    assert out["r"] < -1.5


def test_a_target_touch_is_not_a_fill_but_trading_through_is():
    touch = [_bar(100.0, 104.0, 99.5, 103.0)]
    assert bt.simulate_execution(LONG, touch, MODEL, max_hold=1)["exit"] == "time"
    through = touch + [_bar(103.0, 104.02, 102.5, 103.5)]  # 104 + half spread (0.0104) reached
    out = bt.simulate_execution(LONG, through, MODEL, max_hold=10)
    assert out["exit"] == "target" and out["bars"] == 2 and out["exit_fill"] == 104.0  # no price improvement
    assert out["r"] == pytest.approx((104.0 - 100.04 - (0.0005 * 100.04 + 0.0002 * 104.0)) / 2)  # maker on exit


def test_opens_past_the_stop_or_target_cancel_the_trade():
    past_stop = bt.simulate_execution(LONG, [_bar(97.9, 98.5, 97.0, 98.0)], MODEL, max_hold=10)
    assert past_stop == {"r": 0.0, "exit": "no_fill", "bars": 0, "filled": False, "reason": "opened_past_stop"}
    # 98.0 x 1.0004 = 98.0392 is above the stop, so this one fills
    assert bt.simulate_execution(LONG, [_bar(98.0, 99.0, 98.1, 98.5)], MODEL, max_hold=1)["filled"] is True
    past_target = bt.simulate_execution(LONG, [_bar(104.5, 105.0, 104.0, 104.8)], MODEL, max_hold=10)
    assert past_target["exit"] == "no_fill" and past_target["reason"] == "opened_past_target"


def test_a_short_time_exit_pays_spread_slippage_fees_and_funding():
    model = bt.CostModel(funding_bps_per_8h=1.0)
    bars = [_bar(100.0, 100.8, 99.2, 99.5), _bar(99.5, 100.4, 99.1, 99.3), _bar(99.3, 99.9, 98.9, 99.0)]
    out = bt.simulate_execution(SHORT, bars, model, max_hold=3)
    entry, exit_ = 100.0 * 0.9996, 99.0 * 1.0004
    fees = 0.0005 * (entry + exit_)
    funding = 0.0001 * entry * (3 * 15 / 480)  # 45 minutes of an 8-hour funding period
    assert out["exit"] == "time" and out["bars"] == 3
    assert out["r"] == pytest.approx((entry - exit_ - fees - funding) / 2)
    assert out["friction_r"] == pytest.approx(0.5 - out["r"])  # ideal: (100 - 99) / 2


def test_a_bar_touching_both_is_still_a_loss():
    out = bt.simulate_execution(LONG, [_bar(100.0, 104.5, 97.5, 101.0)], MODEL, max_hold=10)
    assert out["exit"] == "stop"


def test_stats_exclude_unfilled_signals_and_report_costs():
    trades = [{"r": 1.9, "exit": "target", "bars": 2, "filled": True, "fees_r": 0.05, "friction_r": 0.1},
              {"r": -1.1, "exit": "stop", "bars": 1, "filled": True, "fees_r": 0.05, "friction_r": 0.1},
              {"r": 0.0, "exit": "no_fill", "bars": 0, "filled": False}]
    s = bt.stats(trades)
    assert s["trades"] == 2 and s["not_filled"] == 1 and s["expectancy_r"] == 0.4
    assert s["avg_fees_r"] == 0.05 and s["avg_friction_r"] == 0.1
    assert bt.stats([trades[2]]) == {"trades": 0, "not_filled": 1}


def test_the_cli_defaults_to_realistic_execution():
    source = (ROOT / "scripts" / "backtest_zone_rejection.py").read_text(encoding="utf-8")
    assert 'choices=("realistic", "flat"), default="realistic"' in source
    assert bt.CostModel() == bt.CostModel(5.0, 2.0, 2.0, 3.0, 0.0, 15)
