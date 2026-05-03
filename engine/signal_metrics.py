from __future__ import annotations

from typing import Any, Mapping, Optional


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _clamp_ratio(value: Any) -> Optional[float]:
    raw = _safe_float(value)
    if raw is None:
        return None
    if raw < 0:
        return None
    if raw <= 1.0:
        return max(0.0, min(raw, 1.0))
    # Accept percent-style values (0-100) and normalize to ratio.
    if raw <= 100.0:
        return max(0.0, min(raw / 100.0, 1.0))
    return max(0.0, min(raw / 100.0, 1.0))


def resolve_confidence_ratio(signal: Mapping[str, Any]) -> Optional[float]:
    """Resolve a 0..1 confidence ratio from available signal fields."""
    for key in ("confidence", "strength", "confidence_score", "signal_confidence"):
        val = _clamp_ratio(signal.get(key))
        if val is not None:
            return val
    score = _clamp_ratio(signal.get("score"))
    if score is not None:
        return score
    return None


def resolve_score_percent(signal: Mapping[str, Any]) -> Optional[float]:
    """Resolve a 0..100 score percent."""
    score = _safe_float(signal.get("score"))
    if score is not None:
        if score <= 1.0:
            return max(0.0, min(score * 100.0, 100.0))
        return max(0.0, min(score, 100.0))
    conf = resolve_confidence_ratio(signal)
    if conf is not None:
        return max(0.0, min(conf * 100.0, 100.0))
    return None


def resolve_confluence_percent(signal: Mapping[str, Any]) -> Optional[float]:
    """Resolve a 0..100 confluence percent from signal metadata."""
    for key in ("confluence", "confluence_score", "confluence_pct", "confluence_percent"):
        val = _safe_float(signal.get(key))
        if val is not None:
            if val <= 1.0:
                return max(0.0, min(val * 100.0, 100.0))
            return max(0.0, min(val, 100.0))

    count = _safe_float(signal.get("confluence_count") or signal.get("confluence_vote_count"))
    total = _safe_float(signal.get("confluence_total") or signal.get("confluence_total_votes"))
    if count is not None and total and total > 0:
        return max(0.0, min((count / total) * 100.0, 100.0))

    score_norm = _safe_float(signal.get("confluence_score_norm"))
    if score_norm is not None:
        if score_norm <= 1.0:
            return max(0.0, min(score_norm * 100.0, 100.0))
        return max(0.0, min(score_norm, 100.0))

    long_votes = _safe_float(signal.get("long_votes"))
    short_votes = _safe_float(signal.get("short_votes"))
    total_votes = _safe_float(signal.get("total_votes") or signal.get("confluence_total"))
    if total_votes and (long_votes is not None or short_votes is not None):
        top = max(long_votes or 0.0, short_votes or 0.0)
        if total_votes > 0:
            return max(0.0, min((top / total_votes) * 100.0, 100.0))

    return None


def resolve_confluence_total(signal: Mapping[str, Any]) -> Optional[int]:
    """Resolve total confluence vote count if available."""
    for key in ("confluence_total", "confluence_total_votes", "total_votes"):
        val = _safe_float(signal.get(key))
        if val is not None and val > 0:
            return int(val)
    drivers = signal.get("confluence_drivers") or signal.get("drivers") or signal.get("contributors")
    if isinstance(drivers, (list, tuple)):
        return len(drivers)
    return None


def resolve_ml_probability(signal: Mapping[str, Any]) -> Optional[float]:
    """Resolve ML probability as a 0..1 ratio, derived if missing."""
    for key in ("ml_probability", "ml_prob", "ml_score", "ml_confidence"):
        val = _clamp_ratio(signal.get(key))
        if val is not None:
            return val

    components: list[float] = []
    conf = resolve_confidence_ratio(signal)
    if conf is not None:
        components.append(conf)
    score = _clamp_ratio(signal.get("score"))
    if score is not None:
        components.append(score)
    confluence = resolve_confluence_percent(signal)
    if confluence is not None:
        components.append(max(0.0, min(confluence / 100.0, 1.0)))

    if components:
        return sum(components) / len(components)
    return None
