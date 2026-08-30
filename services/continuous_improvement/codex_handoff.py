from __future__ import annotations

from typing import Any

from .recommendation_schema import Recommendation, RecommendationKind


def build_codex_task(recommendation: Recommendation) -> dict[str, Any]:
    """Create an auditable engineering task, never an unattended execution request."""
    return {
        "task_id": f"codex-{recommendation.recommendation_id}",
        "title": recommendation.title,
        "objective": recommendation.rationale,
        "kind": recommendation.kind.value,
        "evidence": list(recommendation.evidence),
        "proposed_change": dict(recommendation.proposed_change),
        "required_workflow": ["branch", "implement", "test", "review", "owner_approval"],
        "production_mutation_authorized": False,
        "real_execution_authorized": False,
    }


def handoff_allowed(recommendation: Recommendation) -> bool:
    return recommendation.kind == RecommendationKind.CODE and bool(recommendation.evidence)
