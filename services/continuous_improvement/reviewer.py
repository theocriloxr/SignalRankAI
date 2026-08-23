from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from services.codex_governance import (
    build_local_codex_recommendations,
    run_external_codex_aggregate_review,
)

from .recommendation_schema import Recommendation, RecommendationKind


def _recommendation_id(kind: RecommendationKind, title: str, change: Mapping[str, Any]) -> str:
    material = json.dumps([kind.value, title, change], sort_keys=True, default=str)
    return "rec-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def normalize_recommendations(review: Mapping[str, Any]) -> tuple[Recommendation, ...]:
    evidence = tuple(str(item) for item in review.get("highest_risk_findings") or ["aggregate_review"])
    results: list[Recommendation] = []
    groups = (
        (RecommendationKind.PARAMETER, "Configuration recommendation", review.get("recommended_env_tweaks") or []),
        (RecommendationKind.CODE, "Engineering recommendation", review.get("recommended_code_changes") or []),
    )
    for kind, prefix, items in groups:
        for item in items:
            title = f"{prefix}: {str(item)[:120]}"
            change = {"proposal": str(item)}
            results.append(
                Recommendation(
                    recommendation_id=_recommendation_id(kind, title, change),
                    kind=kind,
                    title=title,
                    rationale=str(review.get("assessment") or "Evidence-backed review recommendation"),
                    evidence=evidence,
                    proposed_change=change,
                )
            )
    return tuple(results)


async def review_snapshot(snapshot: Mapping[str, Any], *, request_external: bool = False) -> dict[str, Any]:
    local = build_local_codex_recommendations(dict(snapshot))
    external = await run_external_codex_aggregate_review(dict(snapshot)) if request_external else None
    source = external.get("review") if external and external.get("ok") else local
    return {
        "local_review": local,
        "external_review": external,
        "recommendations": normalize_recommendations(source or local),
        "external_status": "completed" if external and external.get("ok") else (
            "failed" if external else "not_requested"
        ),
    }
