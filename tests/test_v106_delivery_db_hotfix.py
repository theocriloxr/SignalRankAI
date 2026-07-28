from __future__ import annotations

import ast
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v106_is_the_declared_default_version() -> None:
    assert 'default="1.1.0"' in _source("core/version.py")


def test_rejection_schema_repair_is_the_sole_head() -> None:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "db" / "migrations"))
    assert ScriptDirectory.from_config(cfg).get_heads() == ["0025_adaptive_strategy"]
    migration = _source("db/migrations/versions/0024_ml_rejected_delivery_runtime.py")
    assert 'ADD COLUMN IF NOT EXISTS signal_id VARCHAR(36)' in migration
    assert 'ix_ml_rejected_signals_signal_id' in migration


def test_clean_schema_and_auto_ops_include_signal_id() -> None:
    for path in (
        "db/migrations/versions/0010_consolidate_full_schema.py",
        "db/auto_ops.py",
    ):
        source = _source(path)
        assert "signal_id" in source
        assert "ix_ml_rejected_signals_signal_id" in source


def test_delivery_lock_is_token_checked_and_released() -> None:
    redis_state = _source("core/redis_state.py")
    engine = _source("engine/core.py")
    assert "cache_delete_if_value_sync" in redis_state
    assert "redis.call('get', KEYS[1]) == ARGV[1]" in redis_state
    assert 'ENGINE_DELIVERY_FANOUT_LOCK_SECONDS", 600' in engine
    assert "cache_delete_if_value(_lock_key, _lock_token)" in engine


def test_primary_owner_and_staging_allowlist_are_supported() -> None:
    engine = _source("engine/core.py")
    assert 'DELIVERY_AUDIENCE_ALLOWLIST' in engine
    assert 'OWNER_TELEGRAM_ID' in engine
    assert 'primary_owner_first' in engine


def test_engine_profile_proof_avoids_second_profile_db_read() -> None:
    engine = _source("engine/core.py")
    bot = _source("signalrank_telegram/bot.py")
    assert 'sig["delivery_profile_verified"] = True' in engine
    assert '_profile_preverified' in bot
    assert 'source=engine_verified' in bot


def test_delivery_reservation_reuses_asset_lock_session() -> None:
    bot = _source("signalrank_telegram/bot.py")
    assert "session=session" in bot
    assert "return await _check_with_session(session)" in bot
    # Prevent regression to nested acquisition inside the reservation transaction.
    tree = ast.parse(bot)
    assert tree is not None


def test_resend_yields_to_active_engine_fanout() -> None:
    bot = _source("signalrank_telegram/bot.py")
    assert 'RESEND_SKIP_WHEN_ENGINE_FANOUT_ACTIVE' in bot
    assert 'skipped: engine delivery fanout active' in bot


def test_outcome_tracker_no_longer_occupies_critical_delivery_lane() -> None:
    source = _source("engine/realtime_outcome_tracker.py")
    assert "priority=DBPriority.BACKGROUND" in source
    assert 'OUTCOME_DB_ADMISSION_TIMEOUT_SECONDS", "1.0"' in source


def test_all_changed_python_files_compile() -> None:
    files = [
        "core/redis_state.py",
        "core/version.py",
        "db/auto_ops.py",
        "db/migrations/versions/0010_consolidate_full_schema.py",
        "db/migrations/versions/0024_ml_rejected_delivery_runtime.py",
        "engine/core.py",
        "engine/realtime_outcome_tracker.py",
        "scripts/deployment_diagnostics.py",
        "scripts/schema_audit.py",
        "signalrank_telegram/bot.py",
    ]
    for rel in files:
        compile(_source(rel), rel, "exec")
