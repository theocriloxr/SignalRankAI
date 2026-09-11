"""Dispatch eligible governed refactors to GitHub's draft-PR workflow."""

from __future__ import annotations

import os
from typing import Any

import httpx

from .recommendation_schema import RecommendationKind, ReviewReport


def _enabled() -> bool:
    return os.getenv("CONTINUOUS_REFACTOR_DISPATCH_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}


def eligible_refactor_recommendation(report: ReviewReport) -> dict[str, Any] | None:
    """Select one bounded external recommendation; local prose never becomes code."""
    for recommendation in report.recommendations:
        targets = list(recommendation.proposed_change.get("target_paths") or [])
        if (
            recommendation.kind == RecommendationKind.CODE
            and recommendation.provider in {"openai", "gemini"}
            and recommendation.risk in {"low", "medium"}
            and targets
            and recommendation.evidence
            and recommendation.acceptance_tests
        ):
            return recommendation.as_dict()
    return None


async def dispatch_refactor_workflow(report: ReviewReport) -> dict[str, Any]:
    if not _enabled():
        return {"ok": True, "dispatched": False, "reason": "disabled"}
    token = os.getenv("CONTINUOUS_REFACTOR_GITHUB_TOKEN", "").strip()
    repository = os.getenv("CONTINUOUS_REFACTOR_GITHUB_REPOSITORY", "").strip()
    if not token or not repository or repository.count("/") != 1:
        return {"ok": False, "dispatched": False, "reason": "github_dispatch_not_configured"}
    recommendation = eligible_refactor_recommendation(report)
    if recommendation is None:
        return {"ok": True, "dispatched": False, "reason": "no_eligible_refactor"}
    body = {
        "event_type": "signalrank_refactor",
        "client_payload": {
            "review_id": report.review_id,
            "dataset_hash": report.dataset_hash,
            "code_sha": report.code_sha,
            "recommendation": recommendation,
        },
    }
    url = f"https://api.github.com/repos/{repository}/dispatches"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                json=body,
            )
            response.raise_for_status()
        return {
            "ok": True,
            "dispatched": True,
            "review_id": report.review_id,
            "recommendation_id": recommendation["recommendation_id"],
        }
    except Exception as exc:
        return {"ok": False, "dispatched": False, "reason": type(exc).__name__}


__all__ = ["dispatch_refactor_workflow", "eligible_refactor_recommendation"]
