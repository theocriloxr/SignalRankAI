from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, Mapping

from services.codex_governance import (
    build_local_codex_recommendations,
    run_external_codex_aggregate_review,
    run_external_gemini_aggregate_review,
)

from .recommendation_schema import Recommendation, RecommendationKind
from .segment_learning import build_segment_learning_recommendations


def _recommendation_id(kind: RecommendationKind, title: str, change: Mapping[str, Any]) -> str:
    material = json.dumps([kind.value, title, change], sort_keys=True, default=str)
    return "rec-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def normalize_recommendations(review: Mapping[str, Any], *, provider: str = "local") -> tuple[Recommendation, ...]:
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
                    provider=provider,
                )
            )
    for item in list(review.get("recommended_refactors") or []):
        if not isinstance(item, Mapping):
            continue
        title = str(item.get("title") or "Bounded code refactor")[:200]
        change = {
            "objective": str(item.get("objective") or ""),
            "target_paths": [str(path) for path in list(item.get("target_paths") or [])],
            "expected_metric": str(item.get("expected_metric") or ""),
            "rollback": str(item.get("rollback") or ""),
        }
        results.append(
            Recommendation(
                recommendation_id=_recommendation_id(RecommendationKind.CODE, title, change),
                kind=RecommendationKind.CODE,
                title=title,
                rationale=str(item.get("objective") or review.get("assessment") or "Evidence-backed refactor"),
                evidence=evidence,
                proposed_change=change,
                risk=str(item.get("risk") or "high"),
                provider=provider,
                acceptance_tests=tuple(str(test) for test in list(item.get("acceptance_tests") or [])),
            )
        )
    return tuple(results)


async def review_snapshot(
    snapshot: Mapping[str, Any],
    *,
    request_external: bool = False,
    request_gemini: bool = False,
) -> dict[str, Any]:
    local = build_local_codex_recommendations(dict(snapshot))
    openai_call = run_external_codex_aggregate_review(dict(snapshot), requested=True) if request_external else _none()
    gemini_call = run_external_gemini_aggregate_review(dict(snapshot), requested=True) if request_gemini else _none()
    external, gemini = await asyncio.gather(openai_call, gemini_call)
    recommendations = list(normalize_recommendations(local, provider="local"))
    recommendations.extend(build_segment_learning_recommendations(
        list(snapshot.get("full_market_segments") or snapshot.get("segments") or [])
    ))
    if external and external.get("ok"):
        recommendations.extend(normalize_recommendations(external.get("review") or {}, provider="openai"))
    if gemini and gemini.get("ok"):
        recommendations.extend(normalize_recommendations(gemini.get("review") or {}, provider="gemini"))
    deduped = {item.recommendation_id: item for item in recommendations}
    statuses = {
        "openai": "completed" if external and external.get("ok") else ("failed" if external else "not_requested"),
        "gemini": "completed" if gemini and gemini.get("ok") else ("failed" if gemini else "not_requested"),
    }
    return {
        "local_review": local,
        "external_review": external,
        "gemini_review": gemini,
        "recommendations": tuple(deduped.values()),
        "external_status": ",".join(f"{name}:{status}" for name, status in statuses.items()),
        "provider_status": statuses,
    }


async def _none() -> None:
    return None
