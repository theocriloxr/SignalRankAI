"""Deterministic, leakage-safe candlestick and price-action evidence.

Candles describe an auction; they do not prove a future move. This module
turns body geometry, wicks, closes, past-only levels, volume and a completed
follow-through candle into an auditable evidence record.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from statistics import median
from typing import Any, Mapping, MutableMapping, Sequence


_TIMEFRAME_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
    "1w": 604800,
}


def _number(value: Any) -> float:
    try:
        number = float(value)
        return number if number == number and number not in {float("inf"), float("-inf")} else 0.0
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _desired_direction(value: str | None, fallback: str) -> str:
    desired = str(value or fallback).strip().lower()
    if desired in {"long", "buy", "bull", "bullish"}:
        return "bullish"
    if desired in {"short", "sell", "bear", "bearish"}:
        return "bearish"
    return "indecision"


def _candle_is_final(candle: Mapping[str, Any], timeframe: str | None = None) -> bool:
    """Resolve completion without assuming that the live tail candle is closed."""
    for key in ("is_final", "is_closed", "closed", "complete"):
        if key in candle:
            value = candle.get(key)
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "closed", "final", "complete"}
            return bool(value)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    for key in ("close_time_ms", "close_timestamp_ms"):
        try:
            value = int(float(candle.get(key)))
            value = value if value > 10_000_000_000 else value * 1000
            return value <= now_ms
        except (TypeError, ValueError):
            pass
    seconds = _TIMEFRAME_SECONDS.get(str(timeframe or "").strip().lower())
    if seconds:
        for key in ("open_time_ms", "timestamp_ms", "timestamp", "time"):
            try:
                opened = int(float(candle.get(key)))
                opened = opened if opened > 10_000_000_000 else opened * 1000
                return opened + (seconds * 1000) <= now_ms
            except (TypeError, ValueError):
                pass
    return False


@dataclass(frozen=True)
class CandleEvidence:
    direction: str
    desired_direction: str
    body_ratio: float
    body_classification: str
    pressure: str
    upper_wick_ratio: float
    lower_wick_ratio: float
    close_location: float
    close_control: str
    rejection: str
    rejection_strength: float
    relative_volume: float | None
    volume_confirmation: bool | None
    support_level: float | None
    resistance_level: float | None
    nearest_level: str | None
    level_distance_atr: float | None
    at_key_level: bool
    range_position: float | None
    market_context: str
    breakout: str
    confirmation: str
    follow_through: str
    aligned_evidence: tuple[str, ...]
    conflicting_evidence: tuple[str, ...]
    evidence_score: int
    evidence_score_pct: float
    state: str
    summary: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _valid_ohlc(candle: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    values = tuple(_number(candle.get(key)) for key in ("open", "high", "low", "close"))
    open_, high, low, close = values
    if low <= 0 or high < low or not (low <= open_ <= high and low <= close <= high):
        return None
    return open_, high, low, close


def _true_ranges(candles: Sequence[Mapping[str, Any]]) -> list[float]:
    values: list[float] = []
    previous_close: float | None = None
    for candle in candles:
        ohlc = _valid_ohlc(candle)
        if ohlc is None:
            continue
        _, high, low, close = ohlc
        value = high - low
        if previous_close is not None:
            value = max(value, abs(high - previous_close), abs(low - previous_close))
        values.append(value)
        previous_close = close
    return values


def _past_levels(history: Sequence[Mapping[str, Any]], close: float) -> tuple[float | None, float | None]:
    """Return nearest support/resistance using only already-confirmed candles."""
    rows = [(i, _valid_ohlc(candle)) for i, candle in enumerate(history)]
    rows = [(i, value) for i, value in rows if value is not None]
    if not rows:
        return None, None
    highs = {i: value[1] for i, value in rows}
    lows = {i: value[2] for i, value in rows}
    pivot_highs: list[float] = []
    pivot_lows: list[float] = []
    for index in range(2, max(2, len(history) - 2)):
        if any(position not in highs for position in range(index - 2, index + 3)):
            continue
        neighbours = [position for position in range(index - 2, index + 3) if position != index]
        if highs[index] >= max(highs[position] for position in neighbours):
            pivot_highs.append(highs[index])
        if lows[index] <= min(lows[position] for position in neighbours):
            pivot_lows.append(lows[index])

    all_highs = [value[1] for _, value in rows]
    all_lows = [value[2] for _, value in rows]
    support_candidates = [level for level in pivot_lows if level <= close] or [min(all_lows)]
    resistance_candidates = [level for level in pivot_highs if level >= close] or [max(all_highs)]
    return max(support_candidates), min(resistance_candidates)


def assess_candle_evidence(
    candles: Sequence[Mapping[str, Any]],
    *,
    focus_index: int = -1,
    direction: str | None = None,
    timeframe: str | None = None,
    level_lookback: int = 40,
    volume_lookback: int = 20,
) -> CandleEvidence:
    """Assess a candle using only information available at the focus close.

    A following candle is used only when it exists after the focus index and is
    final. With the default live focus on the last candle, confirmation is
    always pending.
    """
    if not candles:
        raise ValueError("at least one candle is required")
    index = focus_index if focus_index >= 0 else len(candles) + focus_index
    if index < 0 or index >= len(candles):
        raise IndexError("focus_index is outside the candle sequence")
    candle = candles[index]
    values = _valid_ohlc(candle)
    if values is None:
        raise ValueError("focus candle has invalid OHLC values")
    open_, high, low, close = values
    span = max(high - low, 1e-12)
    body = abs(close - open_)
    body_ratio = body / span
    upper_ratio = (high - max(open_, close)) / span
    lower_ratio = (min(open_, close) - low) / span
    candle_direction = "bullish" if close > open_ else "bearish" if close < open_ else "indecision"
    desired = _desired_direction(direction, candle_direction)

    if body_ratio <= 0.15:
        body_classification, pressure = "indecision", "balanced"
    elif body_ratio >= 0.65:
        body_classification = f"strong_{candle_direction}"
        pressure = "strong_buying" if candle_direction == "bullish" else "strong_selling"
    else:
        body_classification = f"moderate_{candle_direction}"
        pressure = "buying" if candle_direction == "bullish" else "selling"

    close_location = (close - low) / span
    close_control = "buyers" if close_location >= 0.70 else "sellers" if close_location <= 0.30 else "contested"
    if lower_ratio >= 0.45 and lower_ratio >= upper_ratio * 1.5:
        rejection, rejection_strength = "lower_price_rejection", lower_ratio
    elif upper_ratio >= 0.45 and upper_ratio >= lower_ratio * 1.5:
        rejection, rejection_strength = "higher_price_rejection", upper_ratio
    else:
        rejection, rejection_strength = "none", max(upper_ratio, lower_ratio)

    history_start = max(0, index - max(level_lookback, volume_lookback, 14))
    history = list(candles[history_start:index])
    atr_values = _true_ranges(history[-14:])
    atr = sum(atr_values) / len(atr_values) if atr_values else span
    support, resistance = _past_levels(history[-level_lookback:], close)
    support_distance = min(abs(low - support), abs(close - support)) if support is not None else float("inf")
    resistance_distance = min(abs(high - resistance), abs(close - resistance)) if resistance is not None else float("inf")
    support_touched = support is not None and (low <= support <= max(open_, close) or support_distance <= atr * 0.5)
    resistance_touched = resistance is not None and (
        min(open_, close) <= resistance <= high or resistance_distance <= atr * 0.5
    )
    if desired == "bullish" and support is not None:
        nearest_level, raw_distance, at_key_level = "support", support_distance, support_touched
    elif desired == "bearish" and resistance is not None:
        nearest_level, raw_distance, at_key_level = "resistance", resistance_distance, resistance_touched
    elif support_distance <= resistance_distance and support is not None:
        nearest_level, raw_distance, at_key_level = "support", support_distance, support_touched
    elif resistance is not None:
        nearest_level, raw_distance, at_key_level = "resistance", resistance_distance, resistance_touched
    else:
        nearest_level, raw_distance, at_key_level = None, float("inf"), False
    level_distance_atr = raw_distance / max(atr, 1e-12) if raw_distance != float("inf") else None

    valid_history = [value for row in history[-level_lookback:] if (value := _valid_ohlc(row)) is not None]
    historical_low = min((value[2] for value in valid_history), default=low)
    historical_high = max((value[1] for value in valid_history), default=high)
    historical_span = historical_high - historical_low
    range_position = _clamp((close - historical_low) / historical_span) if historical_span > 0 else None
    previous_close = _number(history[-1].get("close")) if history else close
    breakout = "none"
    if resistance is not None and close > resistance and previous_close <= resistance:
        breakout = "bullish_breakout"
    elif support is not None and close < support and previous_close >= support:
        breakout = "bearish_breakdown"
    if breakout != "none":
        market_context = breakout
    elif at_key_level:
        market_context = f"at_{nearest_level}"
    elif range_position is not None and range_position <= 0.25:
        market_context = "lower_range"
    elif range_position is not None and range_position >= 0.75:
        market_context = "upper_range"
    else:
        market_context = "mid_range"

    prior_volumes = [_number(row.get("volume")) for row in history[-volume_lookback:]]
    prior_volumes = [value for value in prior_volumes if value > 0]
    current_volume = _number(candle.get("volume"))
    baseline = median(prior_volumes) if prior_volumes else 0.0
    relative_volume = current_volume / baseline if current_volume > 0 and baseline > 0 else None
    volume_confirmation = relative_volume >= 1.2 if relative_volume is not None else None

    confirmation, follow_through = "pending", "pending"
    following_is_historical = index + 1 < len(candles) - 1
    if index + 1 < len(candles) and (
        following_is_historical or _candle_is_final(candles[index + 1], timeframe)
    ):
        following_values = _valid_ohlc(candles[index + 1])
        if following_values is not None:
            following_open, _, _, following_close = following_values
            if desired == "bullish":
                if following_close < low:
                    confirmation, follow_through = "invalidated", "opposed"
                elif following_close > high:
                    confirmation, follow_through = "confirmed", "strong"
                elif following_close > close and following_close > following_open:
                    confirmation, follow_through = "confirmed", "present"
                else:
                    confirmation, follow_through = "unconfirmed", "absent"
            elif desired == "bearish":
                if following_close > high:
                    confirmation, follow_through = "invalidated", "opposed"
                elif following_close < low:
                    confirmation, follow_through = "confirmed", "strong"
                elif following_close < close and following_close < following_open:
                    confirmation, follow_through = "confirmed", "present"
                else:
                    confirmation, follow_through = "unconfirmed", "absent"
            else:
                confirmation, follow_through = "unconfirmed", "absent"

    aligned_rejection = (desired == "bullish" and rejection == "lower_price_rejection") or (
        desired == "bearish" and rejection == "higher_price_rejection"
    )
    opposing_rejection = (desired == "bullish" and rejection == "higher_price_rejection") or (
        desired == "bearish" and rejection == "lower_price_rejection"
    )
    body_supports = body_ratio >= 0.25 and candle_direction == desired
    body_conflicts = body_ratio >= 0.45 and candle_direction not in {desired, "indecision"}
    close_supports = (desired == "bullish" and close_control == "buyers") or (
        desired == "bearish" and close_control == "sellers"
    )
    close_conflicts = (desired == "bullish" and close_control == "sellers") or (
        desired == "bearish" and close_control == "buyers"
    )
    context_supports = (aligned_rejection and at_key_level) or (
        desired == "bullish" and breakout == "bullish_breakout"
    ) or (desired == "bearish" and breakout == "bearish_breakdown")

    aligned: list[str] = []
    conflicts: list[str] = []
    checks: list[bool] = []
    for label, passed in (
        ("body_pressure", body_supports),
        ("wick_rejection", aligned_rejection),
        ("close_control", close_supports),
        ("location_context", context_supports),
    ):
        checks.append(bool(passed))
        if passed:
            aligned.append(label)
    if relative_volume is not None:
        checks.append(bool(volume_confirmation))
        if volume_confirmation:
            aligned.append("volume_expansion")
    if confirmation != "pending":
        checks.append(confirmation == "confirmed")
        if confirmation == "confirmed":
            aligned.append("next_candle_follow_through")
    if body_conflicts:
        conflicts.append("opposing_body_pressure")
    if opposing_rejection:
        conflicts.append("opposing_wick_rejection")
    if close_conflicts:
        conflicts.append("opposing_close_control")
    if confirmation == "invalidated":
        conflicts.append("next_candle_invalidated")

    positive_count = sum(checks)
    raw_pct = 100.0 * positive_count / max(1, len(checks))
    evidence_score_pct = _clamp(raw_pct - (15.0 * len(conflicts)), 0.0, 100.0)
    state = "invalidated" if confirmation == "invalidated" else (
        "confirmed" if confirmation == "confirmed" and evidence_score_pct >= 60.0 else "observed"
    )
    volume_text = f"volume {relative_volume:.2f}x" if relative_volume is not None else "volume unavailable"
    summary = (
        f"{body_classification.replace('_', ' ')} with {rejection.replace('_', ' ')}; "
        f"close controlled by {close_control}; context {market_context}; {volume_text}; "
        f"next candle {confirmation}. Evidence {evidence_score_pct:.0f}/100, not proof."
    )
    return CandleEvidence(
        direction=candle_direction,
        desired_direction=desired,
        body_ratio=round(body_ratio, 4),
        body_classification=body_classification,
        pressure=pressure,
        upper_wick_ratio=round(upper_ratio, 4),
        lower_wick_ratio=round(lower_ratio, 4),
        close_location=round(close_location, 4),
        close_control=close_control,
        rejection=rejection,
        rejection_strength=round(rejection_strength, 4),
        relative_volume=round(relative_volume, 4) if relative_volume is not None else None,
        volume_confirmation=volume_confirmation,
        support_level=round(support, 8) if support is not None else None,
        resistance_level=round(resistance, 8) if resistance is not None else None,
        nearest_level=nearest_level,
        level_distance_atr=round(level_distance_atr, 4) if level_distance_atr is not None else None,
        at_key_level=at_key_level,
        range_position=round(range_position, 4) if range_position is not None else None,
        market_context=market_context,
        breakout=breakout,
        confirmation=confirmation,
        follow_through=follow_through,
        aligned_evidence=tuple(aligned),
        conflicting_evidence=tuple(conflicts),
        evidence_score=positive_count,
        evidence_score_pct=round(evidence_score_pct, 2),
        state=state,
        summary=summary,
    )


def build_candle_intelligence(
    candles: Sequence[Mapping[str, Any]],
    *,
    direction: str | None = None,
    timeframe: str | None = None,
) -> dict[str, Any]:
    """Return current evidence plus safe previous-candle confirmation."""
    latest_index = len(candles) - 1
    if latest_index > 0 and not _candle_is_final(candles[latest_index], timeframe):
        latest_index -= 1
    latest = assess_candle_evidence(
        candles,
        focus_index=latest_index,
        direction=direction,
        timeframe=timeframe,
    )
    previous: CandleEvidence | None = None
    if latest_index >= 1:
        previous = assess_candle_evidence(
            candles,
            focus_index=latest_index - 1,
            direction=direction,
            timeframe=timeframe,
        )
    selected = previous if previous is not None and previous.state == "confirmed" else latest
    selected_focus = "previous_confirmed" if selected is previous else "latest_observation"
    if selected.state == "invalidated" or selected.evidence_score_pct < 30:
        alignment = "conflicting"
    elif selected.evidence_score_pct >= 60 and not selected.conflicting_evidence:
        alignment = "supportive"
    else:
        alignment = "mixed"
    payload = selected.as_dict()
    payload.update({
        "alignment": alignment,
        "selected_focus": selected_focus,
        "latest": latest.as_dict(),
        "previous": previous.as_dict() if previous is not None else None,
        "confirmation_required": selected.confirmation != "confirmed",
    })
    return payload


def attach_candle_evidence(
    signal: MutableMapping[str, Any],
    candles: Sequence[Mapping[str, Any]],
) -> MutableMapping[str, Any]:
    """Attach normalized candle intelligence; scoring remains centralized."""
    if not candles:
        return signal
    payload = build_candle_intelligence(
        candles,
        direction=str(signal.get("direction") or ""),
        timeframe=str(signal.get("timeframe") or ""),
    )
    signal["candle_evidence"] = payload
    signal["candle_evidence_score"] = payload["evidence_score_pct"]
    signal["candle_evidence_alignment"] = payload["alignment"]
    signal["candle_confirmation"] = payload["confirmation"]
    signal["candle_context"] = payload["market_context"]
    signal["candle_reasoning"] = payload["summary"]
    if payload.get("relative_volume") is not None:
        signal.setdefault("volume_ratio", payload["relative_volume"])
    if payload.get("support_level") is not None:
        signal.setdefault("nearest_support", payload["support_level"])
    if payload.get("resistance_level") is not None:
        signal.setdefault("nearest_resistance", payload["resistance_level"])
    return signal
