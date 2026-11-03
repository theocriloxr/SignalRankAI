"""One rule for a missing or degenerate stop, shared by strategies and the engine repair.

A stop is degenerate when it is missing, on the wrong side of entry, or closer
than SIGNAL_ATR_REPAIR_MIN_ATR_FRACTION (default 0.25) of the asset's own
ATR(14) — inside one bar's noise. Replacement levels follow
AdvancedExitManager's rule on the real ATR: stop at the tighter of recent
structure +/- 0.5 ATR and 2 ATR (2 ATR when structure sits on the entry);
targets 2/3/5 ATR. Pure functions: no I/O.
"""
from __future__ import annotations

import os
from typing import Any, Iterable, Mapping

ATR_PERIOD = 14
TARGET_ATR_MULTIPLES = (2, 3, 5)


def min_atr_fraction() -> float:
    try:
        return float(os.getenv("SIGNAL_ATR_REPAIR_MIN_ATR_FRACTION", "0.25") or 0.25)
    except ValueError:
        return 0.25


def structure_bars() -> int:
    try:
        return max(5, int(os.getenv("SIGNAL_ATR_REPAIR_STRUCTURE_BARS", "20") or 20))
    except ValueError:
        return 20


def ohlc(candles: Iterable[Any]) -> tuple[list[float], list[float], list[float]]:
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    for c in candles or ():
        if not isinstance(c, Mapping):
            continue
        try:
            h, l, cl = float(c.get("high")), float(c.get("low")), float(c.get("close"))
        except (TypeError, ValueError):
            continue
        if h > 0 and l > 0 and cl > 0 and h >= l:
            highs.append(h)
            lows.append(l)
            closes.append(cl)
    return highs, lows, closes


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = ATR_PERIOD) -> float | None:
    if len(closes) < period + 1:
        return None
    trs = [max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
           for i in range(len(closes) - period, len(closes))]
    value = sum(trs) / len(trs)
    return value if value > 0 else None


def stop_is_degenerate(direction: str, entry: float, stop: Any, atr_value: float) -> bool:
    try:
        stop_f = float(stop)
    except (TypeError, ValueError):
        return True
    if not stop_f > 0:
        return True
    long_side = str(direction).lower() in {"long", "buy"}
    wrong_side = stop_f >= entry if long_side else stop_f <= entry
    return wrong_side or abs(entry - stop_f) < min_atr_fraction() * atr_value


def atr_levels(direction: str, entry: float, highs: list[float], lows: list[float],
               atr_value: float) -> tuple[float, list[float]] | None:
    """Replacement stop and targets; None when no valid level exists."""
    long_side = str(direction).lower() in {"long", "buy"}
    window = structure_bars()
    if long_side:
        stop = max(min(lows[-window:]) - 0.5 * atr_value, entry - 2 * atr_value)
        targets = [entry + k * atr_value for k in TARGET_ATR_MULTIPLES]
    else:
        stop = min(max(highs[-window:]) + 0.5 * atr_value, entry + 2 * atr_value)
        targets = [entry - k * atr_value for k in TARGET_ATR_MULTIPLES]
    if stop <= 0 or (long_side and stop >= entry) or (not long_side and stop <= entry):
        return None
    if abs(entry - stop) < min_atr_fraction() * atr_value:
        # Structure sits on top of the entry; fall back to 2 ATR.
        stop = entry - 2 * atr_value if long_side else entry + 2 * atr_value
    if stop <= 0 or any(t <= 0 for t in targets):
        return None
    return stop, targets


__all__ = ["atr", "atr_levels", "min_atr_fraction", "ohlc", "stop_is_degenerate", "structure_bars"]
