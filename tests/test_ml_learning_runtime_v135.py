from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import pytest


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


def test_two_slot_dedicated_role_can_use_zero_foreground_reserve() -> None:
    from db.priority import DBAdmissionController, DBPriority

    controller = DBAdmissionController(
        2,
        foreground_reserve=0,
        background_limit=2,
        analytics_limit=1,
    )
    assert controller.snapshot()["foreground_reserve"] == 0
    assert controller.acquire(DBPriority.BACKGROUND, timeout_s=0.01)
    assert controller.acquire(DBPriority.BACKGROUND, timeout_s=0.01)
    controller.release(DBPriority.BACKGROUND)
    controller.release(DBPriority.BACKGROUND)


def test_session_defaults_zero_reserve_only_for_noninteractive_roles() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "db" / "session.py").read_text(encoding="utf-8")
    role_block = source[source.index("_dedicated_noninteractive_db_roles"):source.index("_default_foreground_reserve")]
    assert '"analytics", "scheduler"' in role_block
    assert "minimum=0" in source
    assert '"worker"' not in role_block
    assert '"delivery"' not in role_block
    assert '"outcome"' not in role_block
    assert '"frontdoor"' not in role_block


def test_analytics_owned_workers_share_analytics_priority_lane() -> None:
    root = Path(__file__).resolve().parents[1]
    asset = (root / "worker" / "asset_learning_worker.py").read_text(encoding="utf-8")
    shadow = (root / "engine" / "shadow_outcome_worker.py").read_text(encoding="utf-8")
    retention = (root / "db" / "storage_maintenance.py").read_text(encoding="utf-8")

    assert 'return "analytics" if role == "analytics" or role.startswith("analytics-") else "background"' in asset
    assert 'return "analytics" if role == "analytics" or role.startswith("analytics-") else "background"' in shadow
    assert 'return "analytics" if role == "analytics" or role.startswith("analytics-") else "background"' in retention
    assert "priority=_learning_db_priority()" in asset
    assert "priority=_shadow_db_priority()" in shadow
    assert "priority=_retention_db_priority()" in retention


def test_ml_candle_hydration_is_bounded_to_training_window() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "ml" / "train_model.py").read_text(encoding="utf-8")

    assert "def _candle_cache_bounds(timeframe: str)" in source
    assert "MarketCandle.open_time_ms >= floor_ms" in source
    assert "ML_CANDLE_FEATURE_BUFFER_BARS" in source
    assert "training_lookback_days * 86400" in source
    assert "[ml_dataset_stage] stage=live_proof_loaded" in source
    assert "[ml_candle_cache]" in source


def test_dedicated_analytics_ml_uses_analytics_priority_and_bounded_wait() -> None:
    root = Path(__file__).resolve().parents[1]
    trainer = (root / "ml" / "train_model.py").read_text(encoding="utf-8")
    artifact_store = (root / "ml" / "artifact_store.py").read_text(encoding="utf-8")
    session = (root / "db" / "session.py").read_text(encoding="utf-8")
    asset_learning = (root / "worker" / "asset_learning_worker.py").read_text(encoding="utf-8")

    assert 'role == "analytics" or role.startswith("analytics-")' in trainer
    assert 'return "analytics"' in trainer
    assert '"drop_if_busy": False' in trainer
    assert "is_analytics and drop_if_busy is not False" in session
    assert "def _dedicated_analytics_min_sessions()" in session
    assert "return max(" in session
    assert '"DB_ANALYTICS_DEDICATED_MIN_CONCURRENT_SESSIONS"' in session
    assert "default_limit = 2 if _dedicated_analytics_role else 1" in session
    assert '"DB_ANALYTICS_MAX_CONCURRENT_SESSIONS"' in session
    assert "requested = max(requested, _dedicated_analytics_min_sessions())" in session
    assert "analytics_limit=_analytics_session_limit" in session
    assert "def _artifact_db_priority()" in artifact_store
    assert 'return "analytics"' in artifact_store
    assert "priority=_artifact_db_priority()" in artifact_store
    assert "ASSET_LEARNING_DB_TIMEOUT_SECONDS" in asset_learning
    assert "drop_if_busy=False" in asset_learning


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
    assert "_outcome_tracker_ml_retrain_owned_here()" in tracker
    assert 'os.getenv("DECOMPOSED_TOPOLOGY_ENABLED", "0")' in tracker
    assert 'role == "analytics" or role.startswith("analytics-")' in tracker


def test_adaptive_and_shadow_writes_are_durable_background_work() -> None:
    root = Path(__file__).resolve().parents[1]
    candle = (root / "engine" / "adaptive" / "candle_store.py").read_text(encoding="utf-8")
    shadow = (root / "engine" / "shadow_outcome_worker.py").read_text(encoding="utf-8")

    # Adaptive candle snapshots are idempotent evidence and must shed pressure
    # instead of holding the engine's tiny DB pool for tens of seconds.
    assert "drop_if_busy=noncritical" in candle
    assert "ADAPTIVE_CANDLE_DB_ADMISSION_TIMEOUT_SECONDS" in candle
    assert "ADAPTIVE_CANDLE_MAX_SNAPSHOTS_PER_TRANSACTION" in candle
    assert "ADAPTIVE_CANDLE_DB_LOCK_TIMEOUT_MS" in candle
    assert "ADAPTIVE_CANDLE_DB_STATEMENT_TIMEOUT_MS" in candle
    assert "SET LOCAL lock_timeout" in candle
    assert "SET LOCAL statement_timeout" in candle
    assert "for item in batch:" in candle
    # Shadow outcome writes remain durable background work because their rows are
    # lifecycle evidence rather than an idempotent candle cache.
    assert shadow.count("drop_if_busy=False") >= 2


@pytest.mark.asyncio
async def test_adaptive_candle_pressure_requeues_full_batch(monkeypatch) -> None:
    from engine.adaptive import candle_store

    while True:
        try:
            candle_store._QUEUE.get_nowait()
        except candle_store.queue.Empty:
            break

    def snapshot(asset: str, open_time_ms: int) -> dict:
        return {
            "asset": asset,
            "timeframe": "1h",
            "provider": "test",
            "candles": [
                {
                    "open_time_ms": open_time_ms,
                    "close_time_ms": open_time_ms + 3_600_000,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 10.0,
                    "is_final": True,
                }
            ],
        }

    original = [snapshot("BTCUSDT", 1_000), snapshot("ETHUSDT", 2_000)]
    for item in original:
        candle_store._QUEUE.put_nowait(item)

    captured: dict[str, object] = {}

    @asynccontextmanager
    async def busy_session(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("simulated DB pressure")
        yield  # pragma: no cover

    monkeypatch.setattr(candle_store, "get_session", busy_session)
    monkeypatch.setenv("ADAPTIVE_CANDLE_MAX_SNAPSHOTS_PER_TRANSACTION", "2")
    monkeypatch.setenv("ADAPTIVE_CANDLE_DB_PRIORITY", "background")

    with pytest.raises(RuntimeError, match="simulated DB pressure"):
        await candle_store.persist_queued_snapshots(12)

    assert captured["priority"] == "background"
    assert captured["drop_if_busy"] is True
    assert float(captured["timeout_seconds"]) <= 0.25
    assert candle_store.queue_depth() == len(original)

    restored = [candle_store._QUEUE.get_nowait() for _ in original]
    assert [item["asset"] for item in restored] == ["BTCUSDT", "ETHUSDT"]


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
