from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from engine.adaptive.types import safe_float


def ohlcv(candles: Sequence[Mapping[str, Any]]):
    opens = [safe_float(c.get("open")) for c in candles]
    highs = [safe_float(c.get("high")) for c in candles]
    lows = [safe_float(c.get("low")) for c in candles]
    closes = [safe_float(c.get("close")) for c in candles]
    volumes = [max(0.0, safe_float(c.get("volume"))) for c in candles]
    return opens, highs, lows, closes, volumes


def atr(candles: Sequence[Mapping[str, Any]], period: int = 14) -> float:
    _, highs, lows, closes, _ = ohlcv(candles)
    if len(closes) < 2:
        return 0.0
    tr = []
    for i in range(1, len(closes)):
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
    tail = tr[-period:]
    return sum(tail) / len(tail) if tail else 0.0


def confirmed_pivots(candles: Sequence[Mapping[str, Any]], window: int = 2):
    _, highs, lows, _, _ = ohlcv(candles)
    pivot_highs: list[tuple[int, float]] = []
    pivot_lows: list[tuple[int, float]] = []
    # The final `window` candles are never eligible, preventing future-confirmation leakage.
    for i in range(window, max(window, len(candles) - window)):
        if highs[i] >= max(highs[i-window:i] + highs[i+1:i+window+1]):
            pivot_highs.append((i, highs[i]))
        if lows[i] <= min(lows[i-window:i] + lows[i+1:i+window+1]):
            pivot_lows.append((i, lows[i]))
    return pivot_highs, pivot_lows


def fingerprint(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def targets(entry: float, stop: float, direction: str, ratios=(1.5, 2.5, 4.0)) -> tuple[float, ...]:
    risk = abs(entry - stop)
    if risk <= 0:
        return ()
    if direction == "LONG":
        return tuple(entry + risk * r for r in ratios)
    return tuple(entry - risk * r for r in ratios)
