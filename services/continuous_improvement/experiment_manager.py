from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class ExperimentState(StrEnum):
    PROPOSED = "proposed"
    BACKTESTED = "backtested"
    WALK_FORWARD_VALIDATED = "walk_forward_validated"
    SHADOW = "shadow"
    PAPER = "paper"
    STAGING_APPROVED = "staging_approved"
    PRODUCTION_ELIGIBLE = "production_eligible"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"


_NEXT = {
    ExperimentState.PROPOSED: {ExperimentState.BACKTESTED, ExperimentState.REJECTED},
    ExperimentState.BACKTESTED: {ExperimentState.WALK_FORWARD_VALIDATED, ExperimentState.REJECTED},
    ExperimentState.WALK_FORWARD_VALIDATED: {ExperimentState.SHADOW, ExperimentState.REJECTED},
    ExperimentState.SHADOW: {ExperimentState.PAPER, ExperimentState.QUARANTINED},
    ExperimentState.PAPER: {ExperimentState.STAGING_APPROVED, ExperimentState.QUARANTINED},
    ExperimentState.STAGING_APPROVED: {ExperimentState.PRODUCTION_ELIGIBLE, ExperimentState.QUARANTINED},
}


@dataclass(frozen=True, slots=True)
class Experiment:
    experiment_id: str
    recommendation_id: str
    state: ExperimentState
    configuration: dict[str, Any]
    dataset_hash: str
    evidence_ids: tuple[str, ...] = ()

    def transition(self, target: ExperimentState, *, evidence_id: str) -> "Experiment":
        if target not in _NEXT.get(self.state, set()):
            raise ValueError(f"illegal_experiment_transition:{self.state}:{target}")
        if not str(evidence_id or "").strip():
            raise ValueError("experiment_transition_evidence_required")
        return Experiment(
            experiment_id=self.experiment_id,
            recommendation_id=self.recommendation_id,
            state=target,
            configuration=dict(self.configuration),
            dataset_hash=self.dataset_hash,
            evidence_ids=(*self.evidence_ids, str(evidence_id)),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def production_activation_allowed(_: Experiment) -> bool:
    """Experiments never activate production; the separate release guard owns that decision."""
    return False
