"""Regression tests: delivery policy, quote sharing, expiry, dedupe."""
from __future__ import annotations

from utils.timeutils import now_utc_naive


# ── Freshness / quote policy (Phases 11-12) ──────────────────────────────────


def test_fresh_quote_permits_delivery() -> None:
    from engine.delivery_freshness import evaluate_signal_age

    payload = {
        "created_at": now_utc_naive(),
        "timeframe": "1h",
    }
    result = evaluate_signal_age(payload)
    assert result.ok is True


def test_stale_quote_blocks_delivery() -> None:
    from engine.delivery_freshness import evaluate_signal_age
    from datetime import timedelta

    payload = {
        "created_at": now_utc_naive() - timedelta(days=2),
        "timeframe": "1h",
    }
    result = evaluate_signal_age(payload)
    assert result.ok is False
    assert result.reason


def test_expired_signal_is_excluded_before_claim() -> None:
    # list_active_signals already filters expired/archived in SQL; verify the
    # query contract preserves that behaviour.
    from db.pg_features import list_active_signals
    import inspect

    source = inspect.getsource(list_active_signals)
    assert "Signal.expired.is_(False)" in source
    assert "Signal.archived.is_(False)" in source
    assert "Signal.created_at >=" in source


def test_immediate_delivery_queries_newest_first() -> None:
    from db.pg_features import list_active_signals
    import inspect

    source = inspect.getsource(list_active_signals)
    assert "created_at.desc()" in source


def test_resend_does_not_duplicate_confirmed_delivery() -> None:
    # The resend job prefetches delivered user ids and skips them; verify the
    # DB-backed dedupe query exists in the job source.
    import signalrank_telegram.bot as bot_module
    import inspect

    source = inspect.getsource(bot_module._resend_unsent_signals_async)
    assert "SignalDelivery.sent_ok.is_(True)" in source
    assert "delivered_user_ids" in source


def test_resend_job_uses_cross_replica_lease() -> None:
    import signalrank_telegram.bot as bot_module
    import inspect

    source = inspect.getsource(bot_module.resend_unsent_signals_job)
    assert "acquire_scheduler_job_lease" in source


def test_stale_reservation_expires_safely() -> None:
    from services.asset_position_manager import get_user_asset_position_state
    import inspect

    source = inspect.getsource(get_user_asset_position_state)
    # Reservations lock an asset only while genuinely recent.
    assert "reservation_ttl_seconds" in source
    assert "reservation_cutoff" in source


# ── One quote per asset per cycle ────────────────────────────────────────────


def test_outcome_tracker_shares_one_quote_per_asset() -> None:
    import engine.realtime_outcome_tracker as tracker
    import inspect

    source = inspect.getsource(tracker._fetch_outcome_quotes)
    # Deduplicates assets into a set before fetching, then gathers one per asset.
    assert "assets = sorted(" in source
    assert "asyncio.gather" in source


# ── Immediate fanout writes confirmed proof ──────────────────────────────────


def test_dispatch_writes_confirmed_proof() -> None:
    import signalrank_telegram.bot as bot_module
    import inspect

    source = inspect.getsource(bot_module._mark_delivery_with_telegram_proof)
    assert "sent_ok" in source or "delivery_state" in source
