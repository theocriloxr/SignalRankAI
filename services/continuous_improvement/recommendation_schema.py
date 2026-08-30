from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class RecommendationKind(StrEnum):
    PARAMETER = "parameter"
    CODE = "code"
    DATA = "data"
    PROVIDER = "provider"
    OPERATIONS = "operations"


class RecommendationStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED_FOR_EXPERIMENT = "approved_for_experiment"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True)
class Recommendation:
    recommendation_id: str
    kind: RecommendationKind
    title: str
    rationale: str
    evidence: tuple[str, ...]
    proposed_change: Mapping[str, Any]
    risk: str = "medium"
    status: RecommendationStatus = RecommendationStatus.PROPOSED
    requires_owner_approval: bool = True
    auto_apply: bool = False

    def __post_init__(self) -> None:
        if not self.recommendation_id or not self.title or not self.rationale:
            raise ValueError("recommendation_identity_required")
        if not self.evidence:
            raise ValueError("recommendation_evidence_required")
        if self.auto_apply:
            raise ValueError("continuous_improvement_cannot_auto_apply")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ReviewReport:
    review_id: str
    period_start: str
    period_end: str
    code_sha: str
    dataset_hash: str
    summary: Mapping[str, Any]
    recommendations: tuple[Recommendation, ...] = field(default_factory=tuple)
    incidents: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    external_review_status: str = "not_requested"
    guardrail: str = "recommendations_only_no_unattended_changes"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
