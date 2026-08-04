from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from core.signal_lifecycle import EXPIRED, SL_HIT, TP2_HIT
from services.outcome_reconciliation import (
    _canonical_outcome,
    _projection_metrics,
    build_outcome_reconciliation_query,
)

ROOT = Path(__file__).resolve().parents[1]


def test_missing_env_bool_regression_is_fixed(monkeypatch) -> None:
    from db import pg_features

    monkeypatch.delenv("OUTCOME_DUPLICATE_NOTIFICATION_SUPPRESSION_ENABLED", raising=False)
    assert pg_features._env_bool("OUTCOME_DUPLICATE_NOTIFICATION_SUPPRESSION_ENABLED", True) is True
    monkeypatch.setenv("OUTCOME_DUPLICATE_NOTIFICATION_SUPPRESSION_ENABLED", "0")
    assert pg_features._env_bool("OUTCOME_DUPLICATE_NOTIFICATION_SUPPRESSION_ENABLED", True) is False
    monkeypatch.setenv("OUTCOME_DUPLICATE_NOTIFICATION_SUPPRESSION_ENABLED", "enabled")
    assert pg_features._env_bool("OUTCOME_DUPLICATE_NOTIFICATION_SUPPRESSION_ENABLED", False) is True


def test_reconciliation_selects_missing_and_stale_outcomes() -> None:
    from datetime import datetime

    stmt = build_outcome_reconciliation_query(cutoff=datetime(2026, 1, 1), limit=100)
    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "outcomes.id IS NULL" in sql
    assert "outcomes.status" in sql
    assert "outcomes.closed_at IS NULL" in sql
    assert "signal_lifecycles.state" in sql
    assert "delivery_confirmed_at" in sql
    assert "delivered_at_utc" in sql


def test_reconciliation_uses_per_signal_savepoints_and_audited_system_corrections() -> None:
    source = (ROOT / "services" / "outcome_reconciliation.py").read_text("utf-8")
    ensure = source[source.index("async def ensure_outcome_projections"):source.index("async def repair_outcome_notification_outbox")]
    outbox = source[source.index("async def repair_outcome_notification_outbox"):source.index("async def outcome_projection_health")]
    assert "async with session.begin_nested()" in ensure
    assert "async with session.begin_nested()" in outbox
    assert '"audited_correction": True' in ensure
    assert '"corrected_by": "system:v1.3.6.9-outcome-reconciliation"' in ensure
    assert "human_corrected" in ensure
    assert "logger.exception" in ensure


def test_partial_stop_projection_uses_protected_partial_accounting() -> None:
    signal = SimpleNamespace(
        entry=100.0,
        stop_loss=99.0,
        direction="long",
        take_profit=[102.0, 103.0, 104.0],
    )
    lifecycle = SimpleNamespace(
        highest_tp_hit=2,
        state=SL_HIT,
        terminal_evidence={"observation_provider": "test"},
        terminal_event_type="sl_hit",
    )
    r_multiple, percent, meta = _projection_metrics(signal, lifecycle, "sl", 100.0)
    assert meta["tp_hit_index"] == 2
    assert meta["partial_exit_policy"] is not None
    assert r_multiple is not None and r_multiple > 0
    assert percent is not None and percent > 0
    assert _canonical_outcome("sl", 2) == "partial_win"


def test_expired_projection_is_non_win_non_loss() -> None:
    signal = SimpleNamespace(entry=100.0, stop_loss=99.0, direction="long")
    lifecycle = SimpleNamespace(
        highest_tp_hit=0,
        state=EXPIRED,
        terminal_evidence={},
        terminal_event_type="expired",
    )
    _r, _pct, meta = _projection_metrics(signal, lifecycle, "expired", 100.0)
    assert meta["tp_hit_index"] == 0
    assert _canonical_outcome("expired", 0) == "expired"


def test_worker_repairs_outcomes_then_notification_outbox() -> None:
    source = (ROOT / "worker" / "worker.py").read_text("utf-8")
    # The worker runs projection reconciliation before the notification-outbox
    # repair, each in its own short DB transaction. Verify the ordering and the
    # logged result across the whole source (the phases were refactored into
    # separate _run_* helpers with independent commits).
    assert source.index("ensure_outcome_projections") < source.index("repair_outcome_notification_outbox")
    assert "outbox_repair.as_dict()" in source


def test_frontdoor_has_terminal_formatting_and_cycle_metrics() -> None:
    source = (ROOT / "signalrank_telegram" / "bot.py").read_text("utf-8")
    assert "[outcome_notify_cycle]" in source
    assert "pending snapshot failed" in source
    assert 'status in {"expired", "time_stop"}' in source
    assert 'status in {"missed", "missed_entry"}' in source
    assert 'status in {"invalid", "invalidated", "cancel", "cancelled", "canceled"}' in source
    assert "Historical reconciliation" in source



def test_outcome_truth_commits_before_notification_outbox() -> None:
    source = (ROOT / "engine" / "realtime_outcome_tracker.py").read_text("utf-8")
    start = source.index("# Commit canonical trading truth before notification fan-out")
    end = source.index("# NEW: Log to ML training data table", start)
    block = source[start:end]
    assert block.index("await session.commit()") < block.index("queue_outcome_notifications_for_outcome")
    assert "outbox queue failed after outcome commit" in block
    assert "await session.rollback()" in block

def test_tracker_logs_persistence_failures_with_traceback_and_signal_context() -> None:
    source = (ROOT / "engine" / "realtime_outcome_tracker.py").read_text("utf-8")
    assert "logger.exception(" in source
    assert "persist_outcome error signal=%s status=%s entry=%s price=%s error=%s" in source




def test_owner_outcome_rebuild_and_audit_commands_are_registered() -> None:
    owner = (ROOT / "signalrank_telegram" / "owner_commands.py").read_text("utf-8")
    bot = (ROOT / "signalrank_telegram" / "bot.py").read_text("utf-8")
    assert "async def outcome_rebuild_command" in owner
    assert "async def outcome_audit_command" in owner
    assert 'CommandHandler("outcome_rebuild"' in bot
    assert 'CommandHandler("outcome_audit"' in bot

def test_resend_budget_exhaustion_uses_cross_replica_backoff() -> None:
    source = (ROOT / "signalrank_telegram" / "bot.py").read_text("utf-8")
    assert 'state.cache_get_sync("resend:budget_backoff_until")' in source
    assert 'state.cache_set_sync(' in source
    assert '"RESEND_BUDGET_BACKOFF_SECONDS", "180"' in source
    assert "job budget exhausted; deferring remaining recipients" not in source

def test_release_identity_is_v1369() -> None:
    version = (ROOT / "core" / "version.py").read_text("utf-8")
    assert 'CODE_VERSION = "1.3.6.9"' in version
    assert "outcome-delivery-recovery-hotfix" in version
