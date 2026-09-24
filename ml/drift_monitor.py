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



def detect_prediction_starvation(
    samples: list[dict[str, Any]],
    *,
    minimum_samples: int = 50,
    minimum_pass_rate: float = 0.01,
) -> dict[str, Any]:
    """Detect persistent model-output starvation without relaxing the certified cutoff."""
    clean: list[tuple[float, float, float, float]] = []
    for item in samples or []:
        if not isinstance(item, dict):
            continue
        try:
            raw = float(item.get("raw_probability"))
            calibrated = float(item.get("calibrated_probability"))
            threshold = float(item.get("threshold"))
            passed = float(item.get("passed"))
        except Exception:
            continue
        if not all(__import__("math").isfinite(v) for v in (raw, calibrated, threshold, passed)):
            continue
        clean.append((raw, calibrated, threshold, passed))

    required = max(10, int(minimum_samples or 50))
    actionable = len(clean) >= required
    if not clean:
        return {
            "actionable": False,
            "starvation_detected": False,
            "samples": 0,
            "minimum_samples": required,
            "minimum_pass_rate": float(minimum_pass_rate),
            "pass_rate": None,
            "raw_max": None,
            "raw_mean": None,
            "calibrated_max": None,
            "threshold_mean": None,
            "threshold_min": None,
        }

    raws = [item[0] for item in clean]
    calibrated = [item[1] for item in clean]
    thresholds = [item[2] for item in clean]
    pass_rate = sum(1 for item in clean if item[3] >= 0.5) / len(clean)
    raw_mean = sum(raws) / len(raws)
    threshold_mean = sum(thresholds) / len(thresholds)
    starvation = bool(
        actionable
        and pass_rate <= max(0.0, min(1.0, float(minimum_pass_rate)))
        and max(raws) < min(thresholds)
    )
    return {
        "actionable": actionable,
        "starvation_detected": starvation,
        "samples": len(clean),
        "minimum_samples": required,
        "minimum_pass_rate": float(minimum_pass_rate),
        "pass_rate": round(pass_rate, 6),
        "raw_max": round(max(raws), 6),
        "raw_mean": round(raw_mean, 6),
        "calibrated_max": round(max(calibrated), 6),
        "threshold_mean": round(threshold_mean, 6),
        "threshold_min": round(min(thresholds), 6),
        "raw_to_threshold_gap": round(max(raws) - min(thresholds), 6),
    }
