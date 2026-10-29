"""The backtest harness must not flatter the strategy (owner strategy evidence, 28 Oct 2026)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bt", ROOT / "scripts" / "backtest_zone_rejection.py")
bt = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bt  # dataclasses resolve annotations through sys.modules
spec.loader.exec_module(bt)

M15 = bt.MS["15m"]


def _bar(i, o, h, l, c):
    return {"timestamp": i * M15, "open": o, "high": h, "low": l, "close": c, "volume": 1.0}


def test_forming_daily_bar_only_uses_closed_15m_bars_so_far():
    day = [_bar(i, 100, 100 + i, 100 - i, 100) for i in range(96)]
    partial = bt.forming_bar(day, 0, now_ms=10 * M15)  # 10 bars have closed
    assert partial["high"] == 109 and partial["low"] == 91  # not the full day's 195/5


def test_market_snapshot_never_contains_future_15m_bars():
    m15 = [_bar(i, 100, 101, 99, 100) for i in range(400)]
    data = {"15m": m15, "4h": [], "1d": []}
    stamps = {tf: [b["timestamp"] for b in rows] for tf, rows in data.items()}
    market = bt.market_at(data, stamps, now_ms=200 * M15)
    assert market["15m"]["candles"][-1]["timestamp"] == 199 * M15
    assert all(c["timestamp"] + M15 <= 200 * M15 for c in market["15m"]["candles"])


def test_a_bar_touching_stop_and_target_is_a_loss_and_costs_are_charged():
    signal = {"direction": "SHORT", "entry": 100.0, "stop_loss": 101.0, "take_profit": 97.0}
    both = [_bar(1, 100, 101.5, 96.5, 98)]
    assert bt.simulate(signal, both, cost_pct=0.1, max_hold=10) == {"r": pytest.approx(-1.1), "exit": "stop", "bars": 1}
    target = [_bar(1, 100, 100.5, 99, 99.5), _bar(2, 99.5, 99.8, 96.9, 97.2)]
    out = bt.simulate(signal, target, cost_pct=0.0, max_hold=10)
    assert out == {"r": pytest.approx(3.0), "exit": "target", "bars": 2}


def test_positions_close_at_market_after_the_holding_limit():
    signal = {"direction": "LONG", "entry": 100.0, "stop_loss": 98.0, "take_profit": 110.0}
    flat = [_bar(i, 100, 101, 99.5, 101) for i in range(1, 6)]
    out = bt.simulate(signal, flat, cost_pct=0.0, max_hold=3)
    assert out == {"r": pytest.approx(0.5), "exit": "time", "bars": 3}


def test_stats_report_expectancy_drawdown_and_profit_factor():
    trades = [{"r": 2.0, "exit": "target", "bars": 4}, {"r": -1.0, "exit": "stop", "bars": 2},
              {"r": -1.0, "exit": "stop", "bars": 3}, {"r": 2.0, "exit": "target", "bars": 5}]
    s = bt.stats(trades)
    assert s["trades"] == 4 and s["win_rate"] == 0.5 and s["expectancy_r"] == 0.5
    assert s["max_drawdown_r"] == 2.0 and s["profit_factor"] == 2.0
    assert bt.stats([]) == {"trades": 0}
