"""Deterministic per-segment learning proposals from completed outcomes."""

from __future__ import annotations

import hashlib
import math
from typing import Any, Mapping, Sequence

from .recommendation_schema import Recommendation, RecommendationKind


def wilson_interval(wins: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 1.0
    proportion = max(0.0, min(1.0, wins / total))
    denominator = 1.0 + (z * z / total)
    centre = proportion + (z * z / (2.0 * total))
    margin = z * math.sqrt((proportion * (1.0 - proportion) / total) + (z * z / (4.0 * total * total)))
    return max(0.0, (centre - margin) / denominator), min(1.0, (centre + margin) / denominator)


def classify_segment(row: Mapping[str, Any], *, minimum_outcomes: int = 20) -> dict[str, Any]:
    wins = max(0, int(row.get("wins") or 0))
    losses = max(0, int(row.get("losses") or 0))
    total = wins + losses
    average_r = float(row.get("avg_r") or 0.0)
    lower, upper = wilson_interval(wins, total)
    if total < minimum_outcomes:
        state, reason = "observe", "insufficient_terminal_sample"
    elif average_r < 0.0 and upper < 0.55:
        state, reason = "shadow_quarantine_candidate", "negative_expectancy_with_weak_win_interval"
    elif average_r > 0.20 and lower > 0.45:
        state, reason = "controlled_expansion_candidate", "positive_expectancy_with_supported_win_interval"
    else:
        state, reason = "hold", "evidence_not_decisive"
    return {
        "asset_class": str(row.get("asset_class") or "unknown"),
        "timeframe": str(row.get("timeframe") or "unknown"),
        "strategy_name": str(row.get("strategy_name") or "unknown"),
        "outcomes": total,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / total if total else 0.0,
        "win_rate_interval_95": [lower, upper],
        "avg_r": average_r,
        "state": state,
        "reason": reason,
    }


def build_segment_learning_recommendations(
    segments: Sequence[Mapping[str, Any]],
    *,
    minimum_outcomes: int = 20,
) -> tuple[Recommendation, ...]:
    recommendations: list[Recommendation] = []
    for raw in segments:
        result = classify_segment(raw, minimum_outcomes=minimum_outcomes)
        if result["state"] not in {"shadow_quarantine_candidate", "controlled_expansion_candidate"}:
            continue
        identity = "/".join((result["asset_class"], result["timeframe"], result["strategy_name"]))
        action = result["state"]
        recommendation_id = "segment-" + hashlib.sha256(f"{identity}:{action}".encode()).hexdigest()[:16]
        evidence = (
            f"segment={identity}",
            f"terminal_outcomes={result['outcomes']}",
            f"avg_r={result['avg_r']:.4f}",
            "win_rate_interval_95=" + ",".join(f"{value:.4f}" for value in result["win_rate_interval_95"]),
        )
        recommendations.append(
            Recommendation(
                recommendation_id=recommendation_id,
                kind=RecommendationKind.PARAMETER,
                title=f"{action.replace('_', ' ').title()}: {identity}",
                rationale=result["reason"],
                evidence=evidence,
                proposed_change={
                    "segment": {
                        "asset_class": result["asset_class"],
                        "timeframe": result["timeframe"],
                        "strategy_name": result["strategy_name"],
                    },
                    "experiment_state": "proposed",
                    "candidate_action": action,
                    "activation": "shadow_only",
                },
                risk="medium",
                provider="deterministic_segment_learner",
                acceptance_tests=(
                    "walk-forward expectancy remains positive after costs",
                    "shadow sample meets the configured minimum outcomes",
                    "max drawdown and loss streak stay inside risk authority limits",
                ),
            )
        )
    return tuple(recommendations)


__all__ = ["build_segment_learning_recommendations", "classify_segment", "wilson_interval"]
