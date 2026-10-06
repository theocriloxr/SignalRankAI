"""Deterministic integrity evidence; unknown provenance is never a pass."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

from .dataset import AdaptiveDatasetRow
from .walk_forward import WalkForwardResult


@dataclass(frozen=True, slots=True)
class IntegrityCheck:
    check_id: str
    status: str
    reason: str
    blocking: bool = True
    source: str = "adaptive_dataset_and_walk_forward"
    severity: str = "material"


def audit_adaptive_dataset(rows: Sequence[AdaptiveDatasetRow], wfo: WalkForwardResult) -> dict:
    checks: list[IntegrityCheck] = []
    def check(name: str, passed: bool, reason: str) -> None:
        checks.append(IntegrityCheck(name, "PASS" if passed else "FAIL", reason))
    check("unique_observations", len({row.signal_id for row in rows}) == len(rows) and bool(rows),
          "signal_ids_must_be_unique")
    check("label_availability", all(row.outcome_known_at is not None and row.outcome_known_at >= row.decision_time for row in rows) and bool(rows),
          "outcome_known_at_required_for_every_label")
    check("purged_chronology", wfo.leakage_checks_passed and bool(wfo.folds),
          "training_decisions_and_labels_must_precede_validation_cutoff")
    check("evidence_separation", len({row.evidence_category for row in rows}) == 1,
          "hypothetical_delivery_and_execution_evidence_must_not_be_pooled")
    check("sequence_lineage", bool(rows) and all(row.sequence_hashes for row in rows),
          "content_references_required_but_not_sufficient_for_point_in_time_verification")
    # A sequence hash is not a replay of indicator availability, universe
    # membership or fills. Existing outcome weighting cannot establish these.
    for name, reason in {
        "lookahead_and_repainting": "feature_and_resampling_availability_replay_required",
        "survivorship": "historical_universe_membership_not_in_outcome_dataset",
        "instrument_costs": "constant_R_cost_is_research_proxy_not_multi_asset_cost_model",
        "execution_fills": "outcome_weighting_is_not_quote_or_order_replay",
        "parameter_selection": "pre_ledger_search_history_requires_independent_reconstruction",
        "regime_coverage": "declared_supported_and_disabled_regimes_need_sample_thresholds",
        "calendar_alignment": "sequence_hashes_do_not_verify_historical_session_and_revision_alignment",
    }.items():
        checks.append(IntegrityCheck(name, "UNVERIFIED", reason))
    return {"method_version": "adaptive-integrity-v1", "checks": [asdict(item) for item in checks],
            "passed": all(item.status in {"PASS", "NOT_APPLICABLE"} or not item.blocking for item in checks),
            "evidence_class": "research", "limitations_explicit": True}
