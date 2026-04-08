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
) -> dict[str, Any]:
    per_feature: dict[str, float] = {}
    drifting: list[str] = []
    for feature, expected_vals in (baseline_features or {}).items():
        actual_vals = (live_features or {}).get(feature) or []
        expected = [_safe_float(v) for v in expected_vals]
        actual = [_safe_float(v) for v in actual_vals]
        score = float(psi(expected, actual, bins=10))
        per_feature[feature] = round(score, 6)
        if score >= float(psi_threshold):
            drifting.append(feature)
    return {
        "drift_detected": bool(drifting),
        "psi_threshold": float(psi_threshold),
        "drifting_features": drifting,
        "psi_scores": per_feature,
    }
