"""Why this rank: named factors and sub-scores for a signal's score (10 Nov 2026).

Learned from the competitor research (Danelfin's "why this AI score" and
Token Metrics' sub-grades): a rank is easier to trust when the trader can see
what moved it. ``engine/scoring.py`` already records every component it weighs
in ``score_components`` as ``{name: {"value": 0..1, "weight": w}}``. This module
turns that into:

* factors: each component as 0-100 with its points, i.e. its share of the
  weighted raw score (value x weight / total weight x 100), strongest first;
* sub-scores: Setup (reward/risk, volatility quality), Technical (confluence,
  price action, regime fit) and Model (ML win probability, strategy
  confidence), each the weighted average of its components, 0-100.

Points add up to the raw weighted score, before the soft cap and calibration
that give the published score, so they explain the rank rather than restate it.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Optional

LABELS = {
    "rr": "Reward/risk",
    "vol": "Volatility quality",
    "confidence": "Strategy confidence",
    "ml_probability": "ML win probability",
    "confluence": "Confluence",
    "candle_evidence": "Price action",
    "regime_fit": "Regime fit",
}
GROUPS = {
    "Setup": ("rr", "vol"),
    "Technical": ("confluence", "candle_evidence", "regime_fit"),
    "Model": ("ml_probability", "confidence"),
}


def _components(signal: Mapping[str, Any]) -> dict[str, tuple[float, float]]:
    raw = signal.get("score_components")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    out: dict[str, tuple[float, float]] = {}
    for name, item in (raw or {}).items() if isinstance(raw, Mapping) else ():
        if name not in LABELS or not isinstance(item, Mapping):
            continue
        try:
            value, weight = float(item.get("value")), float(item.get("weight"))
        except (TypeError, ValueError):
            continue
        if weight > 0 and 0.0 <= value <= 1.0:
            out[name] = (value, weight)
    return out


def rank_factors(signal: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """Factors and sub-scores, or None when the signal carries no score components."""
    components = _components(signal)
    total = sum(weight for _value, weight in components.values())
    if not components or total <= 0:
        return None
    factors = sorted(
        (
            {
                "key": name,
                "label": LABELS[name],
                "value": round(value * 100.0, 1),
                "weight": round(weight / total, 4),
                "points": round(value * weight / total * 100.0, 1),
            }
            for name, (value, weight) in components.items()
        ),
        key=lambda f: f["points"],
        reverse=True,
    )
    sub_scores = {}
    for group, names in GROUPS.items():
        members = [components[n] for n in names if n in components]
        weight = sum(w for _v, w in members)
        if weight > 0:
            sub_scores[group] = round(sum(v * w for v, w in members) / weight * 100.0, 1)
    weakest = min(factors, key=lambda f: f["value"])
    return {
        "raw_score": round(sum(f["points"] for f in factors), 1),
        "factors": factors,
        "sub_scores": sub_scores,
        "weakest": weakest["key"],
        "note": "Points are each factor's share of the raw weighted score, before the soft cap and calibration.",
    }


def rank_factor_lines(signal: Mapping[str, Any]) -> list[str]:
    """Two card lines (Telegram, email): sub-scores, then top drivers and the weakest factor."""
    info = rank_factors(signal)
    if not info:
        return []
    subs = " • ".join(f"{name} {value:.0f}" for name, value in info["sub_scores"].items())
    top = ", ".join(f"{f['label']} {f['value']:.0f} (+{f['points']:.1f})" for f in info["factors"][:2])
    weakest = next(f for f in info["factors"] if f["key"] == info["weakest"])
    lines = [f"🏅 Why this rank: {subs}" if subs else "🏅 Why this rank:"]
    tail = f"   Top: {top}"
    if weakest not in info["factors"][:2]:
        tail += f"; weakest: {weakest['label']} {weakest['value']:.0f}"
    lines.append(tail)
    return lines
