"""Empirical score calibration over the complete observable decision surface.

The calibrator deliberately accepts observations from multiple provenance
domains.  Issued/canonical outcomes receive full weight while counterfactual
shadow outcomes receive a smaller weight.  A chronological holdout prevents a
profile from being labelled validated merely because it fits its training set.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any, Iterable, Mapping, Sequence


PROFILE_STATE_KEY = "signalrankai:score_calibration:shadow_profile"


@dataclass(frozen=True, slots=True)
class ScoreObservation:
    score: float
    won: bool
    source: str
    observed_at: str = ""
    weight: float = 1.0
    asset_class: str = "unknown"
    timeframe: str = "unknown"
    strategy: str = "unknown"
    regime: str = "unknown"


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _pava(values: Sequence[float], weights: Sequence[float]) -> list[float]:
    """Weighted pool-adjacent-violators algorithm for monotonic probabilities."""
    blocks: list[list[float]] = []
    for index, (value, weight) in enumerate(zip(values, weights)):
        blocks.append([float(index), float(index), max(1e-9, weight), value * max(1e-9, weight)])
        while len(blocks) >= 2:
            left, right = blocks[-2], blocks[-1]
            if left[3] / left[2] <= right[3] / right[2]:
                break
            blocks[-2:] = [[left[0], right[1], left[2] + right[2], left[3] + right[3]]]
    result = [0.5] * len(values)
    for start, end, weight, weighted_sum in blocks:
        probability = min(0.995, max(0.005, weighted_sum / weight))
        for index in range(int(start), int(end) + 1):
            result[index] = probability
    return result


def _fit_bins(observations: Sequence[ScoreObservation], *, bins: int, prior_strength: float) -> list[dict[str, Any]]:
    edges = [100.0 * index / bins for index in range(bins + 1)]
    global_weight = sum(max(0.0, item.weight) for item in observations)
    global_wins = sum(max(0.0, item.weight) * float(item.won) for item in observations)
    prior_mean = (global_wins + 1.0) / (global_weight + 2.0)
    rows: list[dict[str, Any]] = []
    raw_probabilities: list[float] = []
    pava_weights: list[float] = []
    for index in range(bins):
        low, high = edges[index], edges[index + 1]
        selected = [
            item for item in observations
            if low <= min(100.0, max(0.0, item.score)) < high or (index == bins - 1 and item.score >= high)
        ]
        weight = sum(max(0.0, item.weight) for item in selected)
        wins = sum(max(0.0, item.weight) * float(item.won) for item in selected)
        probability = (wins + prior_strength * prior_mean) / (weight + prior_strength)
        raw_probabilities.append(probability)
        pava_weights.append(weight + prior_strength)
        rows.append({
            "lower": round(low, 4),
            "upper": round(high, 4),
            "observations": len(selected),
            "weighted_observations": round(weight, 4),
            "weighted_wins": round(wins, 4),
        })
    for row, probability in zip(rows, _pava(raw_probabilities, pava_weights)):
        row["probability"] = round(probability, 6)
    return rows


def _segment_candidates(context: Mapping[str, Any] | None) -> list[str]:
    values = {key: str((context or {}).get(key) or "unknown").strip().lower() for key in (
        "asset_class", "timeframe", "strategy", "regime",
    )}
    strategy = values["strategy"]
    if strategy == "unknown":
        strategy = str((context or {}).get("strategy_name") or "unknown").strip().lower()
    candidates = [
        f"asset_class={values['asset_class']}|timeframe={values['timeframe']}",
        f"strategy={strategy}", f"regime={values['regime']}",
        f"asset_class={values['asset_class']}", f"timeframe={values['timeframe']}",
    ]
    return [key for key in candidates if "=unknown" not in key]


def select_calibration_profile(
    profile: Mapping[str, Any] | None,
    context: Mapping[str, Any] | None = None,
) -> tuple[Mapping[str, Any] | None, str]:
    """Prefer the most specific validated segment, then the global profile."""
    if not profile:
        return None, "unavailable"
    segments = profile.get("segment_profiles")
    if isinstance(segments, Mapping):
        for key in _segment_candidates(context):
            candidate = segments.get(key)
            if isinstance(candidate, Mapping) and candidate.get("validated") and candidate.get("buckets"):
                return candidate, key
    return profile, "global"


def calibrate_score(
    score: float,
    profile: Mapping[str, Any] | None,
    context: Mapping[str, Any] | None = None,
) -> float | None:
    """Map a heuristic 0-100 score to an observed 0-100 win probability."""
    selected, _ = select_calibration_profile(profile, context)
    if not selected or not isinstance(selected.get("buckets"), list):
        return None
    value = min(100.0, max(0.0, _finite(score)))
    for row in selected["buckets"]:
        if not isinstance(row, Mapping):
            continue
        lower, upper = _finite(row.get("lower")), _finite(row.get("upper"), 100.0)
        if lower <= value < upper or (upper >= 100.0 and value <= upper):
            return round(100.0 * min(1.0, max(0.0, _finite(row.get("probability"), 0.5))), 4)
    return None


def _metrics(observations: Sequence[ScoreObservation], buckets: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    if not observations:
        return {"brier_raw": 0.0, "brier_calibrated": 0.0, "ece_raw": 0.0, "ece_calibrated": 0.0}
    profile = {"buckets": list(buckets)}
    total_weight = sum(max(0.0, item.weight) for item in observations) or 1.0
    raw_loss = calibrated_loss = raw_ece = calibrated_ece = 0.0
    for item in observations:
        weight = max(0.0, item.weight)
        actual = float(item.won)
        raw = min(1.0, max(0.0, item.score / 100.0))
        calibrated = (_finite(calibrate_score(item.score, profile), 50.0) / 100.0)
        raw_loss += weight * (raw - actual) ** 2
        calibrated_loss += weight * (calibrated - actual) ** 2
        raw_ece += weight * abs(raw - actual)
        calibrated_ece += weight * abs(calibrated - actual)
    return {
        "brier_raw": round(raw_loss / total_weight, 6),
        "brier_calibrated": round(calibrated_loss / total_weight, 6),
        "ece_raw": round(raw_ece / total_weight, 6),
        "ece_calibrated": round(calibrated_ece / total_weight, 6),
    }


def build_calibration_profile(
    observations: Iterable[ScoreObservation],
    *,
    bins: int = 10,
    minimum_observations: int = 200,
    minimum_holdout: int = 40,
    prior_strength: float = 8.0,
    _include_segments: bool = True,
) -> dict[str, Any]:
    """Fit a monotonic profile and validate it on the newest chronological 20%."""
    clean = [
        item for item in observations
        if 0.0 <= _finite(item.score, -1.0) <= 100.0 and 0.0 < _finite(item.weight) <= 1.0
    ]
    clean.sort(key=lambda item: str(item.observed_at or ""))
    source_counts: dict[str, int] = {}
    for item in clean:
        source_counts[item.source] = source_counts.get(item.source, 0) + 1
    holdout_size = max(minimum_holdout, int(round(len(clean) * 0.20))) if clean else 0
    holdout_size = min(holdout_size, max(0, len(clean) - 1))
    train = clean[:-holdout_size] if holdout_size else clean
    holdout = clean[-holdout_size:] if holdout_size else []
    validation_buckets = _fit_bins(train, bins=max(2, bins), prior_strength=max(0.1, prior_strength)) if train else []
    validation = _metrics(holdout, validation_buckets)
    enough_data = len(clean) >= max(1, minimum_observations) and len(holdout) >= max(1, minimum_holdout)
    improves_brier = validation["brier_calibrated"] <= validation["brier_raw"] + 0.002
    improves_ece = validation["ece_calibrated"] <= validation["ece_raw"] + 0.01
    validated = bool(enough_data and improves_brier and improves_ece)
    final_buckets = _fit_bins(clean, bins=max(2, bins), prior_strength=max(0.1, prior_strength)) if clean else []
    result = {
        "version": "full-market-isotonic-v1",
        "status": "validated_shadow_candidate" if validated else "collecting_evidence",
        "validated": validated,
        "activation": "shadow_only",
        "observations": len(clean),
        "weighted_observations": round(sum(item.weight for item in clean), 4),
        "holdout_observations": len(holdout),
        "minimum_observations": int(minimum_observations),
        "source_counts": source_counts,
        "validation": validation,
        "buckets": final_buckets,
    }
    if _include_segments and clean:
        segment_minimum = max(50, minimum_observations // 2)
        segment_holdout = max(10, minimum_holdout // 2)
        groups: dict[str, list[ScoreObservation]] = {}
        for item in clean:
            fields = {
                "asset_class": item.asset_class, "timeframe": item.timeframe,
                "strategy": item.strategy, "regime": item.regime,
            }
            keys = [
                f"asset_class={fields['asset_class'].lower()}|timeframe={fields['timeframe'].lower()}",
                *[f"{name}={str(value).lower()}" for name, value in fields.items()],
            ]
            for key in keys:
                if "=unknown" not in key:
                    groups.setdefault(key, []).append(item)
        ranked = sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0]))[:50]
        result["segment_profiles"] = {
            key: build_calibration_profile(
                items, bins=bins, minimum_observations=segment_minimum,
                minimum_holdout=segment_holdout, prior_strength=prior_strength,
                _include_segments=False,
            )
            for key, items in ranked if len(items) >= segment_holdout + 1
        }
    return result


def load_shadow_profile() -> dict[str, Any] | None:
    """Read the shared shadow profile without making database access mandatory."""
    try:
        from core.redis_state import state

        raw = state.get_sync(PROFILE_STATE_KEY)
        value = json.loads(raw) if isinstance(raw, str) else raw
        return value if isinstance(value, dict) else None
    except Exception:
        return None


__all__ = [
    "PROFILE_STATE_KEY", "ScoreObservation", "build_calibration_profile",
    "calibrate_score", "load_shadow_profile", "select_calibration_profile",
]
