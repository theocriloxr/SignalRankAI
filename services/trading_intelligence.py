from __future__ import annotations

from typing import Any

from services.market_intelligence import evaluate_market, market_to_signal_fields
from services.mission_control import build_mission_snapshot
from services.mtf_consensus import analyze_mtf_consensus, mtf_to_signal_fields
from services.opportunity_engine import score_opportunity


def _score_breakdown(signal: dict[str, Any]) -> dict[str, float]:
    def _f(value: Any, default: float = 0.0) -> float:
        try:
            value = float(value)
            if 0 <= value <= 1:
                value *= 100.0
            return max(0.0, min(100.0, value))
        except Exception:
            return float(default)

    return {
        "trend": _f(signal.get("mtf_alignment_score"), 55.0),
        "momentum": _f(signal.get("score"), 60.0),
        "liquidity": _f(signal.get("liquidity_score"), 60.0),
        "volume": _f(signal.get("volume_score") or signal.get("relative_volume"), 55.0),
        "regime": _f(signal.get("asset_health_score"), 60.0),
        "historical": _f(signal.get("historical_win_rate") or signal.get("segment_win_rate"), 55.0),
        "ai": _f(signal.get("gemini_review_score") or signal.get("ml_probability"), 60.0),
    }


def enrich_signal_intelligence(
    signal: dict[str, Any],
    *,
    market_data: dict[str, Any] | None = None,
    candles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Attach market, MTF, opportunity, and mission-control context to a signal."""
    sig = dict(signal or {})
    asset = str(sig.get("asset") or sig.get("symbol") or "").upper().strip()
    tf = str(sig.get("timeframe") or "").lower().strip()
    candle_set = candles
    if candle_set is None and market_data and tf:
        tf_data = market_data.get(tf)
        if isinstance(tf_data, dict):
            candle_set = tf_data.get("candles") or []
        elif isinstance(tf_data, list):
            candle_set = tf_data
    try:
        market = evaluate_market(asset, signal=sig, candles=candle_set)
        sig.update(market_to_signal_fields(market))
    except Exception:
        sig.setdefault("asset_class", "unknown")
    try:
        mtf = analyze_mtf_consensus(sig, market_data=market_data)
        sig.update(mtf_to_signal_fields(mtf))
        base_score = float(sig.get("score") or 0.0)
        if base_score:
            sig["score"] = round(max(0.0, min(100.0, base_score * float(sig.get("mtf_confidence_modifier") or 1.0))), 2)
    except Exception:
        pass
    try:
        opportunity = score_opportunity(sig)
        sig["opportunity_score"] = opportunity.score
        sig["opportunity_rank_reason"] = opportunity.rank_reason
        sig["opportunity_components"] = opportunity.components
        sig["opportunity_eligible"] = opportunity.eligible
    except Exception:
        pass
    sig["confidence_breakdown"] = _score_breakdown(sig)
    try:
        mission = build_mission_snapshot(sig)
        sig["trade_health"] = mission.health_score
        sig["mission_recommendation"] = mission.recommendation
        sig["mission_recommendation_reason"] = mission.recommendation_reason
        sig["probability_tp_today"] = mission.probability_tp_today
        sig["probability_recovery"] = mission.probability_recovery
    except Exception:
        pass
    return sig
