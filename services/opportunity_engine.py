from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Iterable

from services.user_intelligence import UserTradingPreferences, risk_profile_settings, signal_matches_preferences


@dataclass(frozen=True, slots=True)
class OpportunityScore:
    asset: str
    score: float
    rank_reason: str
    components: dict[str, float]
    eligible: bool = True
    rejection_reason: str = ""


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _component(signal: dict[str, Any], *keys: str, default: float = 50.0) -> float:
    for key in keys:
        value = signal.get(key)
        if value is not None:
            number = _f(value, default)
            if 0 <= number <= 1:
                number *= 100.0
            return max(0.0, min(100.0, number))
    return default


def score_opportunity(signal: dict[str, Any], prefs: UserTradingPreferences | None = None) -> OpportunityScore:
    sig = dict(signal or {})
    prefs = prefs or UserTradingPreferences()
    pref_ok, pref_reason = signal_matches_preferences(sig, prefs)
    risk_settings = risk_profile_settings(prefs.risk_profile)
    technical = _component(sig, "score", "score_calibrated", "score_final", default=60.0)
    # Prefer calibrated probabilities. Raw model output remains a ranking hint,
    # not a public probability or a substitute for calibration.
    calibrated = sig.get("ml_probability_calibrated")
    if calibrated is not None:
        ai_conf = _component(sig, "ml_probability_calibrated", default=50.0)
    else:
        ai_conf = _component(sig, "gemini_review_score", "ai_review_score", default=50.0)
        raw_model = _component(sig, "ml_probability_raw", "ml_probability", default=50.0)
        ai_conf = (ai_conf * 0.7) + (min(raw_model, 70.0) * 0.3)
    historical = _component(sig, "historical_win_rate", "segment_win_rate", "live_win_rate", default=55.0)
    market = _component(sig, "asset_health_score", "scan_priority", default=60.0)
    rr = _f(sig.get("rr_ratio") or sig.get("rr_estimate") or 0.0)
    rr_score = 70.0
    if rr:
        rr_score = 95.0 if 1.2 <= rr <= 3.5 else 75.0 if rr < 6.0 else 45.0
    time_to_target = _component(sig, "time_to_target_score", default=60.0)
    mtf = _component(sig, "mtf_alignment_score", default=55.0)
    components = {
        "technical": technical,
        "ai": ai_conf,
        "historical": historical,
        "market": market,
        "rr": rr_score,
        "time_to_target": time_to_target,
        "mtf": mtf,
    }
    score = (
        technical * 0.25
        + ai_conf * 0.15
        + historical * 0.15
        + market * 0.15
        + rr_score * 0.10
        + time_to_target * 0.12
        + mtf * 0.08
    )
    base_required = float(os.getenv("PERSONALIZED_BASE_MIN_SCORE", "75") or 75.0)
    required_technical = max(0.0, min(100.0, base_required + float(risk_settings.get("min_score_boost", 0.0))))
    if not pref_ok:
        return OpportunityScore(
            asset=str(sig.get("asset") or sig.get("symbol") or ""),
            score=round(max(0.0, score - 25.0), 1),
            rank_reason=f"Preference block: {pref_reason}",
            components={k: round(v, 1) for k, v in components.items()},
            eligible=False,
            rejection_reason=pref_reason,
        )
    if technical < required_technical:
        reason = f"risk_profile_score_below_{required_technical:.1f}"
        return OpportunityScore(
            asset=str(sig.get("asset") or sig.get("symbol") or ""),
            score=round(max(0.0, score - 15.0), 1),
            rank_reason=f"Risk profile requires technical score {required_technical:.1f}",
            components={k: round(v, 1) for k, v in components.items()},
            eligible=False,
            rejection_reason=reason,
        )
    best_component = max(components.items(), key=lambda item: item[1])
    return OpportunityScore(
        asset=str(sig.get("asset") or sig.get("symbol") or ""),
        score=round(max(0.0, min(100.0, score)), 1),
        rank_reason=f"Best driver: {best_component[0]} {best_component[1]:.0f}/100",
        components={k: round(v, 1) for k, v in components.items()},
    )


def rank_opportunities(signals: Iterable[dict[str, Any]], prefs: UserTradingPreferences | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    ranked: list[tuple[OpportunityScore, dict[str, Any]]] = []
    for signal in signals or []:
        score = score_opportunity(signal, prefs)
        enriched = dict(signal)
        enriched["opportunity_score"] = score.score
        enriched["opportunity_rank_reason"] = score.rank_reason
        enriched["opportunity_components"] = score.components
        enriched["opportunity_eligible"] = score.eligible
        if score.rejection_reason:
            enriched["opportunity_rejection_reason"] = score.rejection_reason
        ranked.append((score, enriched))
    ranked.sort(key=lambda item: (item[0].eligible, item[0].score), reverse=True)
    out = [item[1] for item in ranked if item[0].eligible]
    return out[:limit] if limit else out
