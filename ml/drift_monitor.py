from __future__ import annotations

from typing import Any


def _safe_float(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return d


def psi(expected: list[float], actual: list[float], bins: int = 10) -> float:
    if not expected or not actual:
        return 0.0
    lo = min(min(expected), min(actual))
    hi = max(max(expected), max(actual))
    if hi <= lo:
        return 0.0

    width = (hi - lo) / max(1, bins)
    eps = 1e-8

    def _bucket(arr: list[float]) -> list[float]:
        counts = [0] * bins
        for val in arr:
            idx = int((val - lo) / width)
            if idx >= bins:
                idx = bins - 1
            if idx < 0:
                idx = 0
            counts[idx] += 1
        total = max(1, len(arr))
        return [max(eps, c / total) for c in counts]

    e = _bucket(expected)
    a = _bucket(actual)
    return sum((ai - ei) * __import__("math").log(ai / ei) for ei, ai in zip(e, a))


def detect_feature_drift(
    baseline_features: dict[str, list[float]],
    live_features: dict[str, list[float]],
    psi_threshold: float = 0.25,
    minimum_samples: int = 50,
    minimum_features: int = 5,
) -> dict[str, Any]:
    """Compare baseline and live feature distributions with coverage safeguards.

    Empty or tiny live samples are marked insufficient instead of being treated
    as evidence of no drift. Drift is actionable only after enough independent
    features have adequate sample support.
    """
    per_feature: dict[str, float] = {}
    drifting: list[str] = []
    insufficient: list[str] = []
    evaluated: list[str] = []
    required_samples = max(10, int(minimum_samples or 50))
    for feature, expected_vals in (baseline_features or {}).items():
        actual_vals = (live_features or {}).get(feature) or []
        expected = [_safe_float(v) for v in expected_vals]
        actual = [_safe_float(v) for v in actual_vals]
        if len(expected) < 10 or len(actual) < required_samples:
            insufficient.append(feature)
            continue
        score = float(psi(expected, actual, bins=10))
        per_feature[feature] = round(score, 6)
        evaluated.append(feature)
        if score >= float(psi_threshold):
            drifting.append(feature)
    enough_features = len(evaluated) >= max(1, int(minimum_features or 5))
    return {
        "drift_detected": bool(enough_features and drifting),
        "actionable": bool(enough_features),
        "psi_threshold": float(psi_threshold),
        "minimum_samples": required_samples,
        "minimum_features": max(1, int(minimum_features or 5)),
        "evaluated_features": evaluated,
        "insufficient_features": insufficient,
        "drifting_features": drifting if enough_features else [],
        "psi_scores": per_feature,
    }

