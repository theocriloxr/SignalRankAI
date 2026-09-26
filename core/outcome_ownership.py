"""Canonical ownership contract for SignalRank outcome lifecycle.

There is one live market-observation writer:
    engine.realtime_outcome_tracker.RealtimeOutcomeTracker

Projection reconciliation may repair Outcome rows only from already-persisted
SignalLifecycle evidence. Shadow outcome tracking belongs to the ML/counterfactual
evidence domain and must never mutate canonical delivered-signal lifecycle state.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


TRUE_VALUES = frozenset({"1", "true", "yes", "on", "y"})

CANONICAL_LIVE_OUTCOME_WRITER = "engine.realtime_outcome_tracker"
CANONICAL_PROJECTION_REPAIRER = "services.outcome_reconciliation"
SHADOW_OUTCOME_DOMAIN = "engine.shadow_outcome_worker"
LEGACY_ENGINE_OWNER_FLAG = "ENGINE_OUTCOME_TRACKER_ENABLED"
WORKER_OWNER_FLAG = "WORKER_OUTCOME_TRACKER_ENABLED"
REALTIME_OWNER_ALIAS = "REALTIME_OUTCOME_TRACKER_ENABLED"
RECONCILIATION_FLAG = "OUTCOME_RECONCILIATION_ENABLED"
SHADOW_FLAG = "SHADOW_OUTCOME_TRACKER_ENABLED"


def _truthy(values: Mapping[str, str], key: str, default: bool = False) -> bool:
    if key not in values:
        return default
    return str(values.get(key) or "").strip().lower() in TRUE_VALUES


@dataclass(frozen=True, slots=True)
class OutcomeOwnership:
    live_writer_requested: bool
    projection_reconciliation_enabled: bool
    shadow_tracking_enabled: bool
    legacy_engine_owner_requested: bool
    live_writer: str = CANONICAL_LIVE_OUTCOME_WRITER
    projection_repairer: str = CANONICAL_PROJECTION_REPAIRER
    shadow_domain: str = SHADOW_OUTCOME_DOMAIN

    def as_dict(self) -> dict[str, object]:
        return {
            "live_writer_requested": self.live_writer_requested,
            "projection_reconciliation_enabled": self.projection_reconciliation_enabled,
            "shadow_tracking_enabled": self.shadow_tracking_enabled,
            "legacy_engine_owner_requested": self.legacy_engine_owner_requested,
            "live_writer": self.live_writer,
            "projection_repairer": self.projection_repairer,
            "shadow_domain": self.shadow_domain,
        }


def resolve_outcome_ownership(values: Mapping[str, str]) -> OutcomeOwnership:
    # WORKER_OUTCOME_TRACKER_ENABLED and REALTIME_OUTCOME_TRACKER_ENABLED are
    # compatibility aliases for the same worker-owned RealtimeOutcomeTracker.
    live_writer_requested = _truthy(values, WORKER_OWNER_FLAG, True) or _truthy(
        values, REALTIME_OWNER_ALIAS, False
    )
    return OutcomeOwnership(
        live_writer_requested=live_writer_requested,
        projection_reconciliation_enabled=_truthy(values, RECONCILIATION_FLAG, True),
        shadow_tracking_enabled=_truthy(values, SHADOW_FLAG, False),
        legacy_engine_owner_requested=_truthy(values, LEGACY_ENGINE_OWNER_FLAG, False),
    )


def validate_outcome_ownership(values: Mapping[str, str]) -> list[str]:
    ownership = resolve_outcome_ownership(values)
    errors: list[str] = []

    # The old engine-owner switch no longer starts a tracker and must remain off.
    # Rejecting it at profile validation prevents operators from believing the
    # engine owns lifecycle mutation when the worker/realtime tracker is canonical.
    if ownership.legacy_engine_owner_requested:
        errors.append(
            "ENGINE_OUTCOME_TRACKER_ENABLED is legacy compatibility only; "
            "canonical live outcome ownership belongs to RealtimeOutcomeTracker"
        )

    return errors


__all__ = [
    "CANONICAL_LIVE_OUTCOME_WRITER",
    "CANONICAL_PROJECTION_REPAIRER",
    "SHADOW_OUTCOME_DOMAIN",
    "OutcomeOwnership",
    "resolve_outcome_ownership",
    "validate_outcome_ownership",
]
