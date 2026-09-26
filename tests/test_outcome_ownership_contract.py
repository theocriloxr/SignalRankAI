from __future__ import annotations

from pathlib import Path

from core.outcome_ownership import (
    CANONICAL_LIVE_OUTCOME_WRITER,
    CANONICAL_PROJECTION_REPAIRER,
    SHADOW_OUTCOME_DOMAIN,
    resolve_outcome_ownership,
    validate_outcome_ownership,
)


ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_outcome_owner_aliases_resolve_to_one_live_writer():
    ownership = resolve_outcome_ownership(
        {
            "WORKER_OUTCOME_TRACKER_ENABLED": "1",
            "REALTIME_OUTCOME_TRACKER_ENABLED": "1",
            "ENGINE_OUTCOME_TRACKER_ENABLED": "0",
            "OUTCOME_RECONCILIATION_ENABLED": "1",
            "SHADOW_OUTCOME_TRACKER_ENABLED": "1",
        }
    )
    assert ownership.live_writer_requested is True
    assert ownership.live_writer == CANONICAL_LIVE_OUTCOME_WRITER
    assert ownership.projection_repairer == CANONICAL_PROJECTION_REPAIRER
    assert ownership.shadow_domain == SHADOW_OUTCOME_DOMAIN
    assert ownership.projection_reconciliation_enabled is True
    assert ownership.shadow_tracking_enabled is True


def test_legacy_engine_outcome_owner_flag_is_rejected():
    errors = validate_outcome_ownership(
        {
            "WORKER_OUTCOME_TRACKER_ENABLED": "0",
            "REALTIME_OUTCOME_TRACKER_ENABLED": "0",
            "ENGINE_OUTCOME_TRACKER_ENABLED": "1",
        }
    )
    assert len(errors) == 1
    assert "legacy compatibility only" in errors[0]


def test_realtime_tracker_is_only_production_caller_of_lifecycle_transition_writer():
    allowed = {
        "engine/realtime_outcome_tracker.py",
        "engine/signal_lifecycle.py",  # definition lives here
    }
    offenders: list[str] = []
    for base in ("core", "engine", "services", "worker", "runtime"):
        for path in (ROOT / base).rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if rel in allowed:
                continue
            if "record_lifecycle_event(" in path.read_text(encoding="utf-8"):
                offenders.append(rel)
    assert offenders == []


def test_outcome_reconciliation_is_projection_only_not_market_observation_writer():
    source = _source("services/outcome_reconciliation.py")
    assert "SignalLifecycle" in source
    assert "outcome_status_for_lifecycle" in source
    assert "delivery_projection_reconciliation" in source
    assert "record_lifecycle_event(" not in source
    assert "get_live_price" not in source
    assert "_fetch_final_live_quote" not in source
    assert "fetch_market_data" not in source


def test_shadow_outcome_domain_cannot_mutate_canonical_signal_lifecycle():
    source = _source("engine/shadow_outcome_worker.py")
    assert "MLRejectedSignal" in source
    assert "record_lifecycle_event(" not in source
    assert "SignalLifecycle" not in source


def test_runtime_outcome_role_starts_the_canonical_realtime_tracker():
    source = _source("runtime/outcome.py")
    assert "from engine.realtime_outcome_tracker import RealtimeOutcomeTracker" in source
    assert "tracker=RealtimeOutcomeTracker()" in source


def test_worker_runs_live_writer_and_projection_repair_as_separate_tasks():
    source = _source("worker/worker.py")
    assert '_register_task("outcome_tracker"' in source
    assert '_register_task(\n                "outcome_reconciliation"' in source
    assert "from engine.realtime_outcome_tracker import outcome_tracker" in source
    assert "from services.outcome_reconciliation import (" in source


def test_env_validator_delegates_to_canonical_outcome_ownership_contract():
    source = _source("scripts/validate_env_contract.py")
    assert "from core.outcome_ownership import validate_outcome_ownership" in source
    assert "errors.extend(validate_outcome_ownership(values))" in source
