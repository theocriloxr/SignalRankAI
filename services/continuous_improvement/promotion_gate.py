from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .experiment_manager import Experiment, ExperimentState


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    eligible: bool
    reasons: tuple[str, ...]


def evaluate_production_eligibility(
    experiment: Experiment,
    *,
    owner_approved: bool,
    release_evidence: Mapping[str, bool],
) -> PromotionDecision:
    reasons: list[str] = []
    if experiment.state != ExperimentState.STAGING_APPROVED:
        reasons.append("experiment_not_staging_approved")
    if not owner_approved:
        reasons.append("owner_approval_missing")
    for key in ("tests", "walk_forward", "shadow", "paper", "staging_soak", "rollback"):
        if not bool(release_evidence.get(key)):
            reasons.append(f"evidence_missing:{key}")
    return PromotionDecision(eligible=not reasons, reasons=tuple(reasons))
