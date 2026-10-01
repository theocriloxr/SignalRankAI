from __future__ import annotations

from pathlib import Path

from signalrank_telegram.command_resilience import CommandResponseCache

ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


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
        source.index("def _auto_execute_signal_if_enabled"),
    ]
    assert 'if success:' in proof
    assert 'command_response_cache.delete_prefix(f"signals:{int(telegram_user_id)}:")' in proof


def test_delivery_proven_paper_candidates_do_not_repeat_profile_delivery_filter() -> None:
    source = _source("core/paper_trading_service.py")
    assert source.count('"delivery_proven": True') >= 2
    open_block = source[
        source.index("async def _open_candidate_locked"):
        source.index("async def _notify_paper_decision"),
    ]
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
        source.index("# The database's final admission rule"),
    ]
    assert "confirmed_delivery_count > 0" in block
    assert 'SignalDedupBlocked("delivered_active_thesis"' in block
    assert "existing.expires_at = signal_expires_at" in block
    assert "elif existing.expires_at is None" not in block

    exact = source[
        source.index("exact_active = ("):
        source.index('logger.info(\n        "[dedup] creating canonical signal'),
    ]
    assert "stale_by_time" in exact
    assert "stale_null_expiry" in exact
    assert 'SignalDedupBlocked("active_bucket_conflict"' in exact
    assert "[dedup] exact active bucket reused" not in exact


def test_semantic_dedup_only_reuses_logically_unexpired_rows() -> None:
    source = _source("db/pg_features.py")
    region = source[
        source.index("thesis_cutoff ="):
        source.index("if existing is not None:"),
    ]
    assert region.count("Signal.expires_at > now") >= 2

    secondary = _source("db/repository.py")
    region2 = secondary[
        secondary.index("thesis_cutoff ="):
        secondary.index('opposite = "short"'),
    ]
    assert region2.count("Signal.expires_at > now") >= 2
    assert "expires_at=signal_expires_at" in secondary


def test_active_signals_are_confirmed_delivery_and_lifecycle_authoritative() -> None:
    source = _source("db/pg_features.py")
    block = source[
        source.index("async def list_delivered_signals_for_user"):
        source.index("async def get_delivered_signal_by_ref"),
    ]
    assert ".outerjoin(SignalLifecycle" in block
    assert "lifecycle_active" in block
    assert "active_projection" in block
    assert "SignalDelivery.delivery_confirmed_at.is_not(None)" in block
    assert "CONFIRMED_DELIVERY_STATES" in block
    assert "seen_market_buckets" not in block


def test_missed_entry_is_observation_not_realized_loss() -> None:
    source = _source("engine/realtime_outcome_tracker.py")
    block = source[
        source.index("async def _persist_outcome"):
        source.index("async def _persist_ml_training_data"),
    ]
    assert 'if status_l == "missed_entry":' in block
    assert "missed_entry_observed_r = r_mult" in block
    assert "missed_entry_observed_pct = pct" in block
    assert "r_mult = 0.0" in block
    assert "pct = 0.0" in block
    assert '"missed_entry_observed_r"' in block
    assert '"realized_position_opened": bool(status_l != "missed_entry")' in block


def test_outcome_messages_have_one_notification_owner() -> None:
    source = _source("engine/signal_lifecycle.py")
    helper = source[
        source.index("def _should_queue_event_notification"):
        source.index("def entry_was_touched"),
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
        source.index("async def record_lifecycle_event"),
    ]
    assert "_DEFERRED_LIFECYCLE_OBSERVATIONS.pop(signal_id, None)" in block
    assert "observation_high = max(" in block
    assert "observation_low = min(" in block
    assert "_DEFERRED_LIFECYCLE_OBSERVATIONS[signal_id] = merged" in block
    assert "_DEFERRED_LIFECYCLE_OBSERVATION_LIMIT" in block


def test_paper_worker_rechecks_permanent_skip_after_distributed_lock() -> None:
    source = _source("core/paper_trading_service.py")
    block = source[
        source.index("async def _open_candidate_locked"):
        source.index("async def _notify_paper_decision"),
    ]
    lock_wrapper = source[
        source.index("async def _open_candidate("):
        source.index("async def _open_candidate_locked"),
    ]
    assert "execution_destination_lock" in lock_wrapper
    assert "finalized_skip = (" in block
    assert 'PaperTradeAttempt.decision == "SKIPPED"' in block
    assert "PaperTradeAttempt.retryable.is_(False)" in block
    assert "PaperTradeAttempt.finalized_at.is_not(None)" in block
    assert "finalized skip already recorded" in block
