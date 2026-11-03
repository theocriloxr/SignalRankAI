"""Volatility strategies never emit a stop on the entry (3 Nov 2026).

ATR Breakout, BB Width Volatility and Keltner Volatility put the stop at the
last bar's low; a bar that closes at its low gave entry == stop (production:
LINKUSDT 1d 11.005/11.005, 342 rejections a day). Normal levels are unchanged.
"""
from __future__ import annotations

import pytest

from core import atr_levels
from strategies.volatility import ATRBreakoutStrategy, BBWidthVolatilityStrategy, KeltnerVolatilityStrategy


def _candles(last_low: float, last_close: float, n: int = 30) -> list[dict]:
    rows = [{"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0} for _ in range(n - 1)]
    rows.append({"open": 100.5, "high": 101.5, "low": last_low, "close": last_close})
    return rows


STRATEGIES = [
    (ATRBreakoutStrategy, {"atr": 2.0, "bollinger": {"width": 1.0}}),
    (BBWidthVolatilityStrategy, {"atr": 2.0, "bollinger_width": 0.06, "bollinger": {"width": 0.06}}),
    (KeltnerVolatilityStrategy, {"atr": 2.0, "keltner_width": 0.05}),
]


@pytest.mark.parametrize("strategy, indicators", STRATEGIES)
def test_a_bar_closing_at_its_low_gets_an_atr_stop(strategy, indicators):
    signal = strategy().evaluate({"candles": _candles(last_low=100.0, last_close=100.0), "indicators": indicators})
    assert signal is not None
    entry, stop = signal["entry"], signal["stop"]
    assert stop < entry and entry - stop >= atr_levels.min_atr_fraction() * 2.0
    targets = signal["targets"] if isinstance(signal["targets"], list) else [signal["targets"]]
    assert all(t > entry for t in targets)


@pytest.mark.parametrize("strategy, indicators", STRATEGIES)
def test_a_normal_bar_keeps_its_low_stop_and_2r_target(strategy, indicators):
    signal = strategy().evaluate({"candles": _candles(last_low=98.0, last_close=100.0), "indicators": indicators})
    assert signal is not None
    assert (signal["entry"], signal["stop"], signal["targets"]) == (100.0, 98.0, 104.0)


def test_no_levels_without_an_atr():
    signal = BBWidthVolatilityStrategy().evaluate({"candles": _candles(100.0, 100.0, n=5),
                                                   "indicators": {"bollinger_width": 0.06}})
    assert signal is None


def test_the_shared_rule_matches_the_engine_repair_contract():
    highs, lows, closes = atr_levels.ohlc(_candles(100.0, 100.0))
    atr = atr_levels.atr(highs, lows, closes)
    assert atr and atr_levels.stop_is_degenerate("long", 100.0, 100.0, atr)
    assert not atr_levels.stop_is_degenerate("long", 100.0, 100.0 - atr, atr)
    stop, targets = atr_levels.atr_levels("long", 100.0, highs, lows, atr)
    assert stop == max(min(lows[-20:]) - 0.5 * atr, 100.0 - 2 * atr)
    assert targets == [100.0 + k * atr for k in (2, 3, 5)]
    short_stop, _ = atr_levels.atr_levels("short", 100.0, highs, lows, atr)
    assert short_stop > 100.0
