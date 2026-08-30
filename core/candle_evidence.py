"""Deterministic, leakage-safe candlestick evidence.

Candles describe an auction; they do not prove a future move.  This module
turns their geometry and *past-only* context into an auditable evidence record
that strategies and interfaces can explain consistently.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import median
from typing import Any, Mapping, Sequence


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class CandleEvidence:
    direction: str
    body_ratio: float
    upper_wick_ratio: float
    lower_wick_ratio: float
    close_location: float
    rejection: str
    rejection_strength: float
    relative_volume: float | None
    nearest_level: str | None
    level_distance_atr: float | None
    at_key_level: bool
    confirmation: str
    state: str
    evidence_score: int
    summary: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _true_ranges(candles: Sequence[Mapping[str, Any]]) -> list[float]:
    values: list[float] = []
    previous_close: float | None = None
    for candle in candles:
        high, low, close = (_number(candle.get(k)) for k in ("high", "low", "close"))
        if high < low or high <= 0 or low <= 0:
            continue
        value = high - low
        if previous_close is not None:
            value = max(value, abs(high - previous_close), abs(low - previous_close))
        values.append(value)
        previous_close = close
    return values


def assess_candle_evidence(
    candles: Sequence[Mapping[str, Any]],
    *,
    focus_index: int = -1,
    direction: str | None = None,
    level_lookback: int = 20,
    volume_lookback: int = 20,
) -> CandleEvidence:
    """Assess one completed candle using only information available at its close.

    A following candle is used only when it exists *after* ``focus_index`` and
    is explicitly final.  With the default live focus (the last candle),
    confirmation is always pending.
    """
    if not candles:
        raise ValueError("at least one candle is required")
    index = focus_index if focus_index >= 0 else len(candles) + focus_index
    if index < 0 or index >= len(candles):
        raise IndexError("focus_index is outside the candle sequence")

    candle = candles[index]
    open_, high, low, close = (_number(candle.get(k)) for k in ("open", "high", "low", "close"))
    if low <= 0 or high < low or not (low <= open_ <= high and low <= close <= high):
        raise ValueError("focus candle has invalid OHLC values")
    span = max(high - low, 1e-12)
    body = abs(close - open_)
    upper = high - max(open_, close)
    lower = min(open_, close) - low
    candle_direction = "bullish" if close > open_ else "bearish" if close < open_ else "indecision"
    desired = str(direction or candle_direction).lower()
    if desired in {"long", "buy"}:
        desired = "bullish"
    elif desired in {"short", "sell"}:
        desired = "bearish"

    upper_ratio, lower_ratio = upper / span, lower / span
    close_location = (close - low) / span
    if lower_ratio >= 0.45 and lower_ratio >= upper_ratio * 1.5:
        rejection = "lower_price_rejection"
        rejection_strength = lower_ratio
    elif upper_ratio >= 0.45 and upper_ratio >= lower_ratio * 1.5:
        rejection = "higher_price_rejection"
        rejection_strength = upper_ratio
    else:
        rejection, rejection_strength = "none", max(upper_ratio, lower_ratio)

    history = list(candles[max(0, index - max(level_lookback, volume_lookback, 14)):index])
    atr_values = _true_ranges(history[-14:])
    atr = sum(atr_values) / len(atr_values) if atr_values else span
    level_rows = history[-level_lookback:]
    support = min((_number(row.get("low")) for row in level_rows), default=low)
    resistance = max((_number(row.get("high")) for row in level_rows), default=high)
    support_distance, resistance_distance = abs(close - support), abs(resistance - close)
    if support_distance <= resistance_distance:
        nearest_level, raw_distance = "support", support_distance
    else:
        nearest_level, raw_distance = "resistance", resistance_distance
    level_distance_atr = raw_distance / max(atr, 1e-12) if history else None
    at_key_level = bool(level_distance_atr is not None and level_distance_atr <= 0.5)

    prior_volumes = [_number(row.get("volume")) for row in history[-volume_lookback:]]
    prior_volumes = [value for value in prior_volumes if value > 0]
    current_volume = _number(candle.get("volume"))
    baseline = median(prior_volumes) if prior_volumes else 0.0
    relative_volume = current_volume / baseline if current_volume > 0 and baseline > 0 else None

    confirmation = "pending"
    if index + 1 < len(candles) and bool(candles[index + 1].get("is_final", True)):
        following = candles[index + 1]
        following_close = _number(following.get("close"))
        if desired == "bullish":
            confirmation = "confirmed" if following_close > high else "invalidated" if following_close < low else "unconfirmed"
        elif desired == "bearish":
            confirmation = "confirmed" if following_close < low else "invalidated" if following_close > high else "unconfirmed"
        else:
            confirmation = "unconfirmed"

    aligned_rejection = (desired == "bullish" and rejection == "lower_price_rejection") or (
        desired == "bearish" and rejection == "higher_price_rejection"
    )
    close_supports = (desired == "bullish" and close_location >= 0.65) or (desired == "bearish" and close_location <= 0.35)
    evidence_score = sum((aligned_rejection, close_supports, at_key_level, bool(relative_volume and relative_volume >= 1.2), confirmation == "confirmed"))
    state = "confirmed" if confirmation == "confirmed" and evidence_score >= 3 else "invalidated" if confirmation == "invalidated" else "observed"
    summary = (
        f"{rejection.replace('_', ' ')}; close at {close_location:.0%} of range; "
        f"key-level context {'present' if at_key_level else 'absent'}; "
        f"relative volume {relative_volume:.2f}x; confirmation {confirmation}."
        if relative_volume is not None
        else f"{rejection.replace('_', ' ')}; close at {close_location:.0%} of range; key-level context "
        f"{'present' if at_key_level else 'absent'}; volume unavailable; confirmation {confirmation}."
    )
    return CandleEvidence(
        direction=candle_direction,
        body_ratio=round(body / span, 4),
        upper_wick_ratio=round(upper_ratio, 4),
        lower_wick_ratio=round(lower_ratio, 4),
        close_location=round(close_location, 4),
        rejection=rejection,
        rejection_strength=round(rejection_strength, 4),
        relative_volume=round(relative_volume, 4) if relative_volume is not None else None,
        nearest_level=nearest_level if history else None,
        level_distance_atr=round(level_distance_atr, 4) if level_distance_atr is not None else None,
        at_key_level=at_key_level,
        confirmation=confirmation,
        state=state,
        evidence_score=evidence_score,
        summary=summary,
    )
