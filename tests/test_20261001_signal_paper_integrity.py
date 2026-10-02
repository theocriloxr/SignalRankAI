from __future__ import annotations

from pathlib import Path
import re

from signalrank_telegram.command_resilience import CommandResponseCache

ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _function_block(source: str, name: str) -> str:
    """Extract one function/method regardless of its position in the module."""
    match = re.search(
        rf"(?m)^(?P<indent>[ \t]*)(?:async\s+)?def\s+{re.escape(name)}\s*\(",
        source,
    )
    if match is None:
        raise AssertionError(f"function not found: {name}")
    indent = match.group("indent")
    tail = source[match.end():]
    next_match = re.search(
        rf"(?m)^{re.escape(indent)}(?:(?:async\s+)?def|class)\s+",
        tail,
    )
    end = match.end() + next_match.start() if next_match else len(source)
    return source[match.start():end]


def test_command_cache_can_invalidate_only_one_users_signal_views() -> None:
    cache = CommandResponseCache(max_entries=10, ttl_seconds=60.0)
    cache.set("signals:1409578077:active:7:8:*:all", {"text": "old"})
    cache.set("signals:1409578077:closed:7:8:*:all", {"text": "old closed"})
    cache.set("signals:999:active:7:8:*:all", {"text": "other"})

    assert cache.delete_prefix("signals:1409578077:") == 2
    assert cache.get("signals:1409578077:active:7:8:*:all") is None
    assert cache.get("signals:1409578077:closed:7:8:*:all") is None
    assert cache.get("signals:999:active:7:8:*:all") is not None


def test_confirmed_delivery_invalidates_signals_command_cache() -> None:
    source = _source("signalrank_telegram/bot.py")
    proof = source[
        source.index("async def _mark_delivery_with_telegram_proof"):
        source.index("def _auto_execute_signal_if_enabled")
    ]
    assert 'if success:' in proof
    assert 'command_response_cache.delete_prefix(f"signals:{int(telegram_user_id)}:")' in proof


def test_delivery_proven_paper_candidates_do_not_repeat_profile_delivery_filter() -> None:
    source = _source("core/paper_trading_service.py")
    assert source.count('"delivery_proven": True') >= 2
    open_block = _function_block(source, "_open_candidate_locked")
    assert 'delivery_proven = bool(candidate.get("delivery_proven"))' in open_block
    assert "if not delivery_proven:" in open_block
    assert "signal_matches_preferences(candidate, profile_prefs)" in open_block

    # Paper-specific safety gates remain enforced after delivery eligibility.
    for token in (
        "auto_trade_enabled",
        "paper_daily_loss_limit",
        "max_open_positions",
        "direction_not_allowed",
        "asset_class_not_allowed",
        "entry_deviation_too_large",
        "paper_entry_no_longer_valid",
    ):
        assert token in open_block


def test_delivered_signal_id_cannot_be_recycled_for_a_new_candidate() -> None:
    source = _source("db/pg_features.py")
    block = source[
        source.index("if existing is not None:"):
        source.index("# The database's final admission rule")
    ]
    assert "confirmed_delivery_count > 0" in block
    assert 'SignalDedupBlocked("delivered_active_thesis"' in block
    assert "existing.expires_at = signal_expires_at" in block
    assert "elif existing.expires_at is None" not in block

    exact = source[
        source.index("exact_active = ("):
        source.index('logger.info(\n        "[dedup] creating canonical signal')
    ]
    assert "stale_by_time" in exact
    assert "stale_null_expiry" in exact
    assert 'SignalDedupBlocked("active_bucket_conflict"' in exact
    assert "[dedup] exact active bucket reused" not in exact


def test_semantic_dedup_only_reuses_logically_unexpired_rows() -> None:
    primary = _function_block(_source("db/pg_features.py"), "get_or_create_signal_impl")
    assert primary.count("Signal.expires_at > now") >= 2

    secondary = _function_block(_source("db/repository.py"), "persist_signal")
    assert secondary.count("Signal.expires_at > now") >= 2
    assert "expires_at=signal_expires_at" in secondary


def test_active_signals_are_confirmed_delivery_and_lifecycle_authoritative() -> None:
    source = _source("db/pg_features.py")
    block = source[
        source.index("async def list_delivered_signals_for_user"):
        source.index("async def get_delivered_signal_by_ref")
    ]
    assert ".outerjoin(SignalLifecycle" in block
    assert "lifecycle_active" in block
    assert "active_projection = or_(" in block
    projection = block[block.index("active_projection = or_("):block.index("q: Select")]
    # Entered/TP1/TP2 lifecycle state remains visible even when the original
    # pre-entry setup expiry is in the past. Expiry only guards legacy rows.
    assert projection.index("lifecycle_active") < projection.index("Signal.expires_at")
    assert "~lifecycle_exists" in projection
    assert "SignalDelivery.delivery_confirmed_at.is_not(None)" in block
    assert "CONFIRMED_DELIVERY_STATES" in block
    assert "seen_market_buckets" not in block


def test_missed_entry_is_observation_not_realized_loss() -> None:
    source = _source("engine/realtime_outcome_tracker.py")
    block = _function_block(source, "_persist_outcome")
    assert 'if status_l == "missed_entry":' in block
    assert "missed_entry_observed_r = r_mult" in block
    assert "missed_entry_observed_pct = pct" in block
    assert "r_mult = None" in block
    assert "pct = None" in block
    assert '"missed_entry_observed_r"' in block
    assert '"realized_position_opened": bool(status_l != "missed_entry")' in block


def test_outcome_messages_have_one_notification_owner() -> None:
    source = _source("engine/signal_lifecycle.py")
    helper = source[
        source.index("def _should_queue_event_notification"):
        source.index("def entry_was_touched")
    ]
    for event in (
        "tp1_hit", "tp2_hit", "tp3_hit", "sl_hit", "breakeven_stop",
        "missed_entry", "expired",
    ):
        assert f'"{event}"' in helper
    assert "LIFECYCLE_OUTCOME_NOTIFICATIONS_ENABLED" in helper


def test_transient_lifecycle_observations_are_merged_for_retry() -> None:
    source = _source("engine/signal_lifecycle.py")
    block = source[
        source.index("async def update_lifecycle_observation"):
        source.index("async def record_lifecycle_event")
    ]
    assert "_DEFERRED_LIFECYCLE_OBSERVATIONS.pop(signal_id, None)" in block
    assert "observation_high = max(" in block
    assert "observation_low = min(" in block
    assert "_DEFERRED_LIFECYCLE_OBSERVATIONS[signal_id] = merged" in block
    assert "_DEFERRED_LIFECYCLE_OBSERVATION_LIMIT" in block


def test_paper_worker_rechecks_permanent_skip_after_distributed_lock() -> None:
    source = _source("core/paper_trading_service.py")
    block = _function_block(source, "_open_candidate_locked")
    lock_wrapper = _function_block(source, "_open_candidate")
    assert "execution_destination_lock" in lock_wrapper
    assert "finalized_skip = (" in block
    assert 'PaperTradeAttempt.decision == "SKIPPED"' in block
    assert "PaperTradeAttempt.retryable.is_(False)" in block
    assert "PaperTradeAttempt.finalized_at.is_not(None)" in block
    assert "finalized skip already recorded" in block


def test_delivery_receipt_round_trip_preserves_exact_signal_snapshot() -> None:
    from delivery.receipts import DeliveryReceipt
    from delivery.service import DeliveryOperation

    operation = DeliveryOperation(
        user_id=123,
        signal_id="sig-immutable",
        channel_id=123,
        signal_version="1",
        delivery_kind="signal",
    )
    snapshot = {
        "signal_id": "sig-immutable",
        "asset": "US30",
        "timeframe": "15m",
        "direction": "SELL",
        "entry": 50686.17,
        "stop_loss": 50877.72,
        "take_profits": [50134.51, 49582.84, 49031.18],
        "generated_at": "2026-10-01T14:14:00+00:00",
    }
    receipt = DeliveryReceipt.accepted(
        operation,
        message_id=56763,
        mode="sent",
        signal_snapshot=snapshot,
    )
    restored = DeliveryReceipt.from_dict(receipt.as_dict())
    assert restored.signal_snapshot == snapshot
    assert restored.as_dict()["signal_snapshot"]["entry"] == 50686.17


def test_delivery_proof_persists_snapshot_generated_time_not_mutable_signal_row() -> None:
    source = _source("db/pg_features.py")
    block = _function_block(source, "mark_signal_delivery_result")
    assert "_delivery_snapshot_from_proof(telegram_api_result)" in block
    assert '_delivery_snapshot_datetime(proof_snapshot.get("generated_at"))' in block
    assert "or getattr(signal_row, \"created_at\", None)" in block


def test_paper_candidate_uses_exact_delivery_snapshot_levels_and_expiry() -> None:
    source = _source("core/paper_trading_service.py")
    candidates = _function_block(source, "_telegram_delivery_candidates")
    assert "_proof_signal_snapshot(delivery)" in candidates
    assert '_proof_datetime(snapshot.get("generated_at"))' in candidates
    assert '_proof_datetime(snapshot.get("expires_at"))' in candidates
    assert '_snapshot_or(snapshot, "entry", signal.entry)' in candidates
    assert '_snapshot_or(snapshot, "stop_loss", signal.stop_loss)' in candidates
    assert "snapshot_targets" in candidates

    open_block = _function_block(source, "_open_candidate_locked")
    assert "expires_at=candidate.get(\"expires_at\")" in open_block


def test_staging_oct1_incident_replay_is_fail_closed_and_behavior_complete() -> None:
    replay = (ROOT / "scripts/staging_oct1_incident_replay.py").read_text(encoding="utf-8")
    assert 'EXPECTED_STAGING_PROJECT = "8d21a09b-8e45-4c10-87dd-e3568441153f"' in replay
    assert 'if env != "staging"' in replay
    assert '"staging_project_pin_mismatch"' in replay
    assert '"global_execution_kill_switch_off"' in replay
    assert '"unsafe_live_flags="' in replay
    assert "paper_trading_service._telegram_delivery_candidates" in replay
    assert "paper_trading_service._open_candidate(candidate, snapshot_entry)" in replay
    assert "paper_trading_service._notify_paper_decision = _noop_notification" in replay
    assert "list_delivered_signals_for_user" in replay
    assert '_persist_outcome(missed_id, "missed_entry", 53.09, 53.575)' in replay
    for assertion_name in (
        "ordinary_profile_would_reject",
        "snapshot_entry_restored",
        "snapshot_generated_at_restored",
        "paper_first_opened",
        "duplicate_open_prevented",
        "signals_command_projection_contains_active_signal",
        "no_profile_mismatch_attempt",
        "no_signal_stale_attempt",
        "missed_entry_realized_r_null",
        "missed_entry_pnl_pct_null",
        "missed_entry_marks_no_realized_position",
    ):
        assert f'"{assertion_name}"' in replay
    assert '"retained_evidence": True' in replay
    assert '"external_notifications_sent": False' in replay
    assert '"broker_orders_submitted": False' in replay


def test_outcome_tracker_uses_exact_delivery_snapshot_levels_for_us30() -> None:
    from types import SimpleNamespace
    from engine.realtime_outcome_tracker import _tracked_signal_payload

    mutable_row = SimpleNamespace(
        signal_id="ed8d33a2-be1",
        asset="US30",
        direction="short",
        entry=51321.24,
        stop_loss=51484.80,
        take_profit=[50850.19],
        created_at=None,
        expires_at=None,
        timeframe="15m",
        score=78.3,
        ml_probability=0.477,
    )
    snapshot = {
        "signal_id": "ed8d33a2-be1",
        "asset": "US30",
        "timeframe": "15m",
        "direction": "SELL",
        "entry": 50686.17,
        "stop_loss": 50877.72,
        "take_profits": [50134.51, 49582.84, 49031.18],
        "generated_at": "2026-10-01T14:14:00+00:00",
        "expires_at": "2026-10-02T14:14:00+00:00",
        "score": 85.2,
    }
    payload = _tracked_signal_payload(
        mutable_row,
        None,
        None,
        snapshot,
        reason="verified_delivery_snapshot",
    )
    assert payload["entry"] == 50686.17
    assert payload["stop_loss"] == 50877.72
    assert payload["take_profit"] == [50134.51, 49582.84, 49031.18]
    assert payload["score"] == 85.2
    assert payload["delivery_snapshot_authoritative"] is True


def test_outcome_tracker_detects_conflicting_recipient_trade_terms() -> None:
    from engine.realtime_outcome_tracker import _delivery_snapshot_signature

    first = {
        "asset": "US30",
        "direction": "SELL",
        "timeframe": "15m",
        "entry": 50686.17,
        "stop_loss": 50877.72,
        "take_profits": [50134.51, 49582.84, 49031.18],
    }
    same = dict(first)
    conflicting = {
        **first,
        "entry": 51321.24,
        "stop_loss": 51484.80,
        "take_profits": [50850.19],
    }
    assert _delivery_snapshot_signature(first) == _delivery_snapshot_signature(same)
    assert _delivery_snapshot_signature(first) != _delivery_snapshot_signature(conflicting)


def test_outcome_tracker_quarantines_conflicting_delivery_snapshots_before_tracking() -> None:
    source = _source("engine/realtime_outcome_tracker.py")
    helper = _function_block(source, "_confirmed_delivery_snapshot_map")
    assert "previous != signature" in helper
    assert "conflicts.add(sid)" in helper
    assert "snapshots.pop(sid, None)" in helper
    assert "[outcome_snapshot_conflict]" in helper

    active = _function_block(source, "_fetch_active_signals")
    assert "_confirmed_delivery_snapshot_map" in active
    assert "if str(signal_row.signal_id) not in conflicts" in active
    assert "_tracked_signal_payload(" in active


def test_staging_oct1_replay_materializes_orm_evidence_before_session_close() -> None:
    replay = _source("scripts/staging_oct1_incident_replay.py")
    verify = replay[
        replay.index('label="certification.oct1.verify"'):
        replay.index("# Use the real outcome tracker")
    ]
    assert "position_evidence = [" in verify
    assert "attempt_reasons = [" in verify
    assert verify.index("position_evidence = [") < verify.index("await session.rollback()")
    assert verify.index("attempt_reasons = [") < verify.index("await session.rollback()")
    assert 'position["signal_entry"]' in verify
    assert 'position["stop_loss"]' in verify
    assert "position.signal_entry" not in verify
    assert "position.stop_loss" not in verify


def test_staging_oct1_replay_materializes_outcome_before_session_close() -> None:
    replay = _source("scripts/staging_oct1_incident_replay.py")
    block = replay[
        replay.index('label="certification.oct1.outcome_verify"'):
        replay.index("failed = sorted")
    ]
    assert "outcome_evidence = {" in block
    assert block.index("outcome_evidence = {") < block.index("await session.rollback()")
    for field in ("r_multiple", "percent", "pnl_pct", "meta"):
        assert f'"{field}"' in block
    assert 'outcome_evidence["r_multiple"]' in block
    assert 'outcome_evidence["pnl_pct"]' in block
    assert "outcome.r_multiple" not in block[block.index("await session.rollback()"):]
    assert "outcome.pnl_pct" not in block[block.index("await session.rollback()"):]
