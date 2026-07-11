from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


TF_ORDER = ("1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d", "1w")
TF_LEVEL = {tf: idx for idx, tf in enumerate(TF_ORDER)}


@dataclass(frozen=True, slots=True)
class TimeframeBias:
    timeframe: str
    bias: str
    confidence: float


@dataclass(frozen=True, slots=True)
class MultiTimeframeConsensus:
    execution_timeframe: str
    direction: str
    higher_timeframe_bias: str
    lower_timeframe_bias: str
    aligned_timeframes: tuple[str, ...] = ()
    conflicting_timeframes: tuple[str, ...] = ()
    bias_by_timeframe: tuple[TimeframeBias, ...] = ()
    alignment_score: float = 50.0
    confidence_modifier: float = 1.0
    trade_type: str = "Unclassified"
    explanation: str = ""


def _as_direction(value: Any) -> str:
    raw = str(value or "").lower().strip()
    return "short" if raw in {"short", "sell", "bearish"} else "long"


def _direction_bias(direction: str) -> str:
    return "bearish" if direction == "short" else "bullish"


def _candle_close(candle: dict[str, Any]) -> float | None:
    try:
        return float(candle.get("close"))
    except Exception:
        return None


def infer_timeframe_bias(candles: list[dict[str, Any]] | None, timeframe: str) -> TimeframeBias:
    closes = [_candle_close(c) for c in (candles or [])]
    closes = [x for x in closes if x is not None]
    if len(closes) < 20:
        return TimeframeBias(timeframe=timeframe, bias="neutral", confidence=0.0)
    fast_n = min(10, len(closes))
    slow_n = min(30, len(closes))
    fast = sum(closes[-fast_n:]) / fast_n
    slow = sum(closes[-slow_n:]) / slow_n
    latest = closes[-1]
    drift = (latest - closes[-fast_n]) / max(abs(closes[-fast_n]), 1e-9)
    if latest > fast >= slow:
        bias = "bullish"
    elif latest < fast <= slow:
        bias = "bearish"
    elif fast > slow:
        bias = "bullish"
    elif fast < slow:
        bias = "bearish"
    else:
        bias = "neutral"
    confidence = min(100.0, max(20.0, abs((fast - slow) / max(abs(slow), 1e-9)) * 20000.0 + abs(drift) * 800.0))
    return TimeframeBias(timeframe=timeframe, bias=bias, confidence=round(confidence, 1))


def analyze_mtf_consensus(
    signal: dict[str, Any],
    market_data: dict[str, Any] | None = None,
) -> MultiTimeframeConsensus:
    direction = _as_direction(signal.get("direction"))
    desired_bias = _direction_bias(direction)
    execution_tf = str(signal.get("timeframe") or "1h").lower().strip()
    data = market_data or {}
    biases: list[TimeframeBias] = []
    for tf in TF_ORDER:
        tf_data = data.get(tf)
        candles = None
        if isinstance(tf_data, dict):
            candles = tf_data.get("candles")
        elif isinstance(tf_data, list):
            candles = tf_data
        if candles:
            biases.append(infer_timeframe_bias(candles, tf))
    if not biases:
        return MultiTimeframeConsensus(
            execution_timeframe=execution_tf,
            direction=direction,
            higher_timeframe_bias="neutral",
            lower_timeframe_bias="neutral",
            trade_type="Single-timeframe setup",
            explanation="No higher-timeframe candle set available for consensus.",
        )

    current_level = TF_LEVEL.get(execution_tf, TF_LEVEL["1h"])
    higher = [b for b in biases if TF_LEVEL.get(b.timeframe, 99) > current_level]
    lower = [b for b in biases if TF_LEVEL.get(b.timeframe, -1) < current_level]
    higher_votes = _weighted_bias(higher)
    lower_votes = _weighted_bias(lower)
    aligned = tuple(b.timeframe for b in biases if b.bias == desired_bias)
    conflicting = tuple(b.timeframe for b in biases if b.bias not in {"neutral", desired_bias})
    total = len(aligned) + len(conflicting)
    alignment = (len(aligned) / total * 100.0) if total else 50.0
    higher_bias = higher_votes or "neutral"
    lower_bias = lower_votes or "neutral"
    if higher_bias == desired_bias and alignment >= 65:
        trade_type = "Trend continuation"
        modifier = 1.05
    elif higher_bias not in {"neutral", desired_bias} and (lower_bias in {"neutral", desired_bias} or execution_tf in aligned):
        trade_type = "Counter-trend pullback"
        modifier = 0.86
    elif higher_bias == desired_bias and lower_bias not in {"neutral", desired_bias}:
        trade_type = "Pullback inside higher-timeframe trend"
        modifier = 0.94
    elif alignment < 50:
        trade_type = "Mixed-timeframe conflict"
        modifier = 0.82
    else:
        trade_type = "Mixed confluence"
        modifier = 0.97
    explanation = (
        f"{execution_tf} {direction.upper()} with HTF {higher_bias}; "
        f"aligned={len(aligned)} conflicting={len(conflicting)}."
    )
    return MultiTimeframeConsensus(
        execution_timeframe=execution_tf,
        direction=direction,
        higher_timeframe_bias=higher_bias,
        lower_timeframe_bias=lower_bias,
        aligned_timeframes=aligned,
        conflicting_timeframes=conflicting,
        bias_by_timeframe=tuple(biases),
        alignment_score=round(alignment, 1),
        confidence_modifier=round(modifier, 3),
        trade_type=trade_type,
        explanation=explanation,
    )


def _weighted_bias(biases: list[TimeframeBias]) -> str:
    if not biases:
        return ""
    score = {"bullish": 0.0, "bearish": 0.0, "neutral": 0.0}
    for bias in biases:
        weight = max(1.0, bias.confidence)
        score[bias.bias] = score.get(bias.bias, 0.0) + weight
    return max(score.items(), key=lambda item: item[1])[0]


def mtf_to_signal_fields(consensus: MultiTimeframeConsensus) -> dict[str, Any]:
    return {
        "mtf_higher_bias": consensus.higher_timeframe_bias,
        "mtf_lower_bias": consensus.lower_timeframe_bias,
        "mtf_alignment_score": consensus.alignment_score,
        "mtf_confidence_modifier": consensus.confidence_modifier,
        "trade_type": consensus.trade_type,
        "mtf_aligned_timeframes": list(consensus.aligned_timeframes),
        "mtf_conflicting_timeframes": list(consensus.conflicting_timeframes),
        "mtf_explanation": consensus.explanation,
        "mtf_bias_by_timeframe": [
            {"timeframe": b.timeframe, "bias": b.bias, "confidence": b.confidence}
            for b in consensus.bias_by_timeframe
        ],
    }
