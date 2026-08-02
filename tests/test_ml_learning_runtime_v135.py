from __future__ import annotations

from pathlib import Path


def test_large_pool_allows_background_without_consuming_foreground_reserve() -> None:
    from db.priority import DBAdmissionController, DBPriority

    controller = DBAdmissionController(
        16,
        foreground_reserve=4,
        background_limit=4,
        analytics_limit=1,
        analytics_enabled=True,
    )
    assert controller.acquire(DBPriority.INTERACTIVE, timeout_s=0.01)
    assert controller.acquire(DBPriority.CRITICAL, timeout_s=0.01)
    for _ in range(4):
        assert controller.acquire(DBPriority.BACKGROUND, timeout_s=0.01)

    snapshot = controller.snapshot()
    assert snapshot["foreground_reserve"] == 4
    assert snapshot["classes"]["interactive"]["limit"] == 2
    assert snapshot["classes"]["critical"]["limit"] == 2
    assert snapshot["classes"]["background"]["active"] == 4
    assert snapshot["active_total"] == 6

    for _ in range(4):
        controller.release(DBPriority.BACKGROUND)
    controller.release(DBPriority.CRITICAL)
    controller.release(DBPriority.INTERACTIVE)


def test_two_slot_pool_keeps_strict_foreground_protection() -> None:
    from db.priority import DBAdmissionController, DBPriority

    controller = DBAdmissionController(2)
    assert controller.acquire(DBPriority.CRITICAL, timeout_s=0.01)
    assert not controller.acquire(DBPriority.BACKGROUND, timeout_s=0, nonblocking=True)
    assert controller.acquire(DBPriority.INTERACTIVE, timeout_s=0.01)
    controller.release(DBPriority.INTERACTIVE)
    controller.release(DBPriority.CRITICAL)


def test_ml_training_is_nonblocking_and_multisource() -> None:
    root = Path(__file__).resolve().parents[1]
    trainer = (root / "ml" / "train_model.py").read_text(encoding="utf-8")
    tracker = (root / "engine" / "realtime_outcome_tracker.py").read_text(encoding="utf-8")

    assert '"source_type": "shadow_rejected"' in trainer
    assert '"source_type": "paper_execution"' in trainer
    assert "await asyncio.to_thread(" in trainer
    assert "[ml_training_run]" in trainer
    assert 'drop_if_busy": False' in trainer
    assert 'name="ml-retrain"' in tracker
    assert "self._run_ml_retrain()" in tracker


def test_adaptive_and_shadow_writes_are_durable_background_work() -> None:
    root = Path(__file__).resolve().parents[1]
    candle = (root / "engine" / "adaptive" / "candle_store.py").read_text(encoding="utf-8")
    shadow = (root / "engine" / "shadow_outcome_worker.py").read_text(encoding="utf-8")

    assert "drop_if_busy=False" in candle
    assert candle.count("ADAPTIVE_CANDLE_DB_TIMEOUT_SECONDS") >= 1
    assert shadow.count("drop_if_busy=False") >= 2


def test_secondary_evidence_trains_candidate_without_live_promotion() -> None:
    root = Path(__file__).resolve().parents[1]
    trainer = (root / "ml" / "train_model.py").read_text(encoding="utf-8")
    engine_ml = (root / "engine" / "ml.py").read_text(encoding="utf-8")
    artifact_store = (root / "ml" / "artifact_store.py").read_text(encoding="utf-8")

    assert "continuing with secondary evidence" in trainer
    assert "status=candidate_only" in trainer
    assert "status=candidate_saved" in trainer
    assert 'model_name="candidate"' in trainer
    assert "reload_shadow_model" in engine_ml
    assert 'model_name: str = "primary"' in artifact_store


def test_startup_restores_primary_and_candidate_artifacts() -> None:
    root = Path(__file__).resolve().parents[1]
    startup = (root / "db" / "auto_ops.py").read_text(encoding="utf-8")
    assert 'model_name="primary"' in startup
    assert 'model_name="candidate"' in startup
    assert "ML_RESTORE_ACTIVE_ARTIFACT_ON_STARTUP" in startup
    assert "ML_RESTORE_CANDIDATE_ARTIFACT_ON_STARTUP" in startup
