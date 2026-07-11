from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from engine.signal_metrics import (
    resolve_confluence_percent,
    resolve_ml_probability,
    resolve_score_percent,
)


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _parse_tp_levels(raw: Any) -> List[float]:
    if isinstance(raw, list):
        values: List[float] = []
        for item in raw:
            if isinstance(item, dict):
                for key in ("price", "tp", "target", "level"):
                    value = _safe_float(item.get(key))
                    if value is not None and value > 0:
                        values.append(value)
                        break
                continue
            value = _safe_float(item)
            if value is not None and value > 0:
                values.append(value)
        return values
    value = _safe_float(raw)
    return [value] if value is not None and value > 0 else []


def _format_pct(value: Optional[float], digits: int = 1) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}%"


def _format_number(value: Optional[float], digits: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}"


def _unique_texts(values: Iterable[Any], limit: int = 4) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def build_signal_explanation(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Build a transparent, user-facing explanation for a signal."""
    score = resolve_score_percent(signal)
    if score is None:
        score = _safe_float(signal.get("score")) or 0.0
    ml_probability = resolve_ml_probability(signal)
    confluence = resolve_confluence_percent(signal)
    regime = str(signal.get("regime") or signal.get("market_regime") or "").strip()
    technical_reason = str(
        signal.get("technical_reason")
        or signal.get("trade_logic")
        or signal.get("setup_rationale")
        or signal.get("reasoning")
        or ""
    ).strip()

    score_components = signal.get("score_components") if isinstance(signal.get("score_components"), dict) else {}
    entry = _safe_float(signal.get("entry"))
    stop_loss = _safe_float(signal.get("stop_loss") or signal.get("stop"))
    tp_levels = _parse_tp_levels(signal.get("take_profit") or signal.get("tp_levels") or signal.get("targets"))
    rr = _safe_float((score_components or {}).get("rr_ratio"))
    if rr is None and entry and stop_loss and tp_levels:
        rr = abs(tp_levels[-1] - entry) / max(1e-9, abs(entry - stop_loss))
    if rr is None:
        rr = _safe_float(signal.get("rr_ratio") or signal.get("rr_estimate"))

    drivers = _unique_texts(signal.get("confluence_drivers") or signal.get("drivers") or [])
    def _component_value(name: str) -> Optional[float]:
        value = score_components.get(name)
        if isinstance(value, dict):
            value = value.get("value")
        return _safe_float(value)

    metric_drivers: List[str] = []
    if rr is not None:
        metric_drivers.append(f"R/R 1:{rr:.2f}")
    confluence_component = _component_value("confluence")
    if confluence_component is not None:
        metric_drivers.append(f"Confluence component {confluence_component * 100.0:.0f}%")
    confidence_component = _component_value("confidence")
    if confidence_component is not None:
        metric_drivers.append(f"Confidence component {confidence_component * 100.0:.0f}%")
    volatility_component = _component_value("vol")
    if volatility_component is not None:
        metric_drivers.append(f"Volatility quality {volatility_component * 100.0:.0f}%")
    if score_components.get("regime_bonus") not in (None, 1, 1.0):
        metric_drivers.append(f"Regime bonus x{float(score_components['regime_bonus']):.2f}")
    if score_components.get("ml_boost") not in (None, 1, 1.0):
        metric_drivers.append(f"ML boost x{float(score_components['ml_boost']):.2f}")
    if not drivers:
        drivers = []
    drivers = _unique_texts(list(drivers) + metric_drivers)

    invalidation = signal.get("invalidation") or signal.get("invalidation_level")
    if isinstance(invalidation, list):
        invalidation = " | ".join(str(item) for item in invalidation if item is not None)
    invalidation_text = str(invalidation or "").strip()

    summary_parts: List[str] = []
    if technical_reason:
        summary_parts.append(technical_reason)
    elif drivers:
        summary_parts.append("; ".join(drivers[:3]))
    if not summary_parts:
        if score >= 85:
            summary_parts.append("High-conviction setup")
        elif score >= 70:
            summary_parts.append("Qualified setup")
        else:
            summary_parts.append("Lower-conviction setup")

    bullets: List[str] = []
    if regime:
        bullets.append(f"Regime: {regime}")
    if confluence is not None:
        bullets.append(f"Confluence: {int(confluence)}%")
    if ml_probability is not None:
        bullets.append(f"ML probability: {ml_probability * 100.0:.0f}%")
    if rr is not None:
        bullets.append(f"Estimated R/R: 1:{rr:.2f}")
    if drivers:
        bullets.extend(drivers[:3])
    if invalidation_text:
        bullets.append(f"Invalidation: {invalidation_text[:120]}")
    
    # Add confidence components from ranking if available
    conf_components = signal.get("confidence_components") or signal.get("score_breakdown") or {}
    if conf_components.get("trend_confidence") is not None:
        bullets.append(f"Trend Score: {conf_components.get('trend_confidence'):.0f}")
    if conf_components.get("liquidity_confidence") is not None:
        bullets.append(f"Liquidity Score: {conf_components.get('liquidity_confidence'):.0f}")
    if conf_components.get("volume_confidence") is not None:
        bullets.append(f"Volume Score: {conf_components.get('volume_confidence'):.0f}")
    if conf_components.get("ml_confidence") is not None:
        bullets.append(f"ML Score: {conf_components.get('ml_confidence'):.0f}")
    if conf_components.get("regime_confidence") is not None:
        bullets.append(f"Regime Score: {conf_components.get('regime_confidence'):.0f}")
    if conf_components.get("composite_score") is not None:
        bullets.append(f"Composite: {conf_components.get('composite_score'):.0f}")

    # Why this signal was generated
    why_generated = []
    if technical_reason:
        why_generated.append(technical_reason)
    if regime:
        why_generated.append(f"Market in {regime} regime")
    if confluence and confluence > 60:
        why_generated.append("Strong confluence detected")
    if ml_probability and ml_probability > 0.7:
        why_generated.append("High ML conviction")
    
    # What confirms/invalidates it
    confirms = []
    if confluence and confluence > 50:
        confirms.append("Strong confluence")
    if ml_probability and ml_probability > 0.6:
        confirms.append("ML validates")
    if regime and regime != "RANGING":
        confirms.append(f"Favorable {regime} regime")
    
    invalidates = []
    if invalidation_text:
        invalidates.append(invalidation_text[:80])
    if regime == "RANGING":
        invalidates.append("Sideways market")
    if confluence and confluence < 30:
        invalidates.append("Weak confluence")

    return {
        "score": float(score or 0.0),
        "label": "High-conviction setup" if score >= 85 else "Qualified setup" if score >= 70 else "Lower-conviction setup",
        "summary": ". ".join(summary_parts[:2]),
        "bullets": _unique_texts(bullets, limit=6),
        "technical_reason": technical_reason or None,
        "regime": regime or None,
        "confluence": confluence,
        "ml_probability": ml_probability,
        "risk_reward": rr,
        "drivers": drivers,
        "invalidation": invalidation_text or None,
        "score_components": score_components,
        "why_generated": why_generated,
        "confirms": confirms,
        "invalidates": invalidates,
    }
