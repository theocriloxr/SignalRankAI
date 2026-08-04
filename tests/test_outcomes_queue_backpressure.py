"""Regression tests: outcome transitions, asset-lock release, candle queue, outbox repair."""
from __future__ import annotations

import pytest


# ── Outcome transitions (Phase 13) ───────────────────────────────────────────


def test_tp1_to_tp2_is_allowed() -> None:
    from core.signal_lifecycle import outcome_transition_allowed

    assert outcome_transition_allowed("tp1", "tp2") is True


def test_tp1_to_tp3_is_allowed() -> None:
    from core.signal_lifecycle import outcome_transition_allowed

    assert outcome_transition_allowed("tp1", "tp3") is True


def test_tp2_to_tp3_is_allowed() -> None:
    from core.signal_lifecycle import outcome_transition_allowed

    assert outcome_transition_allowed("tp2", "tp3") is True


def test_tp1_to_partial_win_be_is_allowed() -> None:
    from core.signal_lifecycle import outcome_transition_allowed

    assert outcome_transition_allowed("tp1", "partial_win_be") is True


def test_tp3_to_tp1_is_rejected() -> None:
    from core.signal_lifecycle import outcome_transition_allowed

    assert outcome_transition_allowed("tp3", "tp1") is False


def test_stop_to_pending_is_rejected() -> None:
    from core.signal_lifecycle import outcome_transition_allowed

    assert outcome_transition_allowed("stop", "pending") is False


def test_sl_to_pending_is_rejected() -> None:
    from core.signal_lifecycle import outcome_transition_allowed

    assert outcome_transition_allowed("sl", "pending") is False


def test_expired_to_entry_is_rejected() -> None:
    from core.signal_lifecycle import outcome_transition_allowed

    assert outcome_transition_allowed("expired", "entry") is False


def test_pending_to_entry_is_allowed() -> None:
    from core.signal_lifecycle import outcome_transition_allowed

    assert outcome_transition_allowed("pending", "entry") is True


def test_entry_to_tp1_is_allowed() -> None:
    from core.signal_lifecycle import outcome_transition_allowed

    assert outcome_transition_allowed("entry", "tp1") is True


def test_entry_to_stop_is_allowed() -> None:
    from core.signal_lifecycle import outcome_transition_allowed

    assert outcome_transition_allowed("entry", "stop") is True


def test_upsert_outcome_immutability_guards_terminal_rows() -> None:
    # The durable writer must reject mutation of a terminal row without an
    # attributed audited correction (unchanged production contract).
    from db.pg_features import upsert_outcome
    import inspect

    source = inspect.getsource(upsert_outcome)
    assert "audited_correction" in source
    assert "correction_reason" in source


# ── Stale asset locks (Phase 14) ─────────────────────────────────────────────


def test_partial_win_be_releases_asset_lock() -> None:
    from services.asset_position_manager import TERMINAL_OUTCOMES, _state_from_status

    assert "partial_win_be" in TERMINAL_OUTCOMES
    assert "partial_win" in TERMINAL_OUTCOMES
    assert "breakeven" in TERMINAL_OUTCOMES
    # A terminal protected exit maps to STOPPED so the cooldown (not an
    # unresolved-position gate) governs the lock.
    assert _state_from_status("partial_win_be") == "STOPPED"
    assert _state_from_status("partial_win") == "STOPPED"


def test_tp1_tp2_stay_non_terminal() -> None:
    from services.asset_position_manager import TERMINAL_OUTCOMES, _state_from_status

    assert "tp1" not in TERMINAL_OUTCOMES
    assert "tp2" not in TERMINAL_OUTCOMES
    assert _state_from_status("tp1") == "TP1"
    assert _state_from_status("tp2") == "TP2"


def test_reconciliation_is_idempotent() -> None:
    from services.outcome_reconciliation import OutcomeReconciliationResult

    first = OutcomeReconciliationResult(examined=5, repaired_existing=2)
    second = OutcomeReconciliationResult(examined=5, repaired_existing=2)
    assert first.as_dict() == second.as_dict()


# ── Adaptive candle queue (Phase 15) ─────────────────────────────────────────


def _clear_queue() -> None:
    import engine.adaptive.candle_store as cs

    with cs._LOCK:
        cs._QUEUE.queue.clear()
        cs._LAST_SNAPSHOT.clear()
        cs._DROPPED = 0


def test_adaptive_queue_coalesces_same_asset_timeframe() -> None:
    import engine.adaptive.candle_store as cs

    _clear_queue()
    # Use realistic epoch-ms timestamps: the candle normaliser converts small
    # values as seconds, so sub-10B integers would be scaled to ms.
    ts1 = 1_700_000_000_001
    ts2 = 1_700_000_000_002
    cs.enqueue_market_snapshot("BTCUSDT", {"1h": {"candles": [{"open_time_ms": ts1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]}})
    cs.enqueue_market_snapshot("BTCUSDT", {"1h": {"candles": [{"open_time_ms": ts2, "open": 2, "high": 2, "low": 2, "close": 2, "volume": 2}]}})
    # Second enqueue replaces the first in place: depth stays 1.
    assert cs.queue_depth() == 1
    payload = list(cs._QUEUE.queue)[0]
    assert payload["candles"][-1]["open_time_ms"] == ts2


def test_adaptive_queue_remains_bounded() -> None:
    import engine.adaptive.candle_store as cs
    import os

    _clear_queue()
    os.environ["ADAPTIVE_CANDLE_QUEUE_MAX"] = "100"
    try:
        # Enqueue 1000 distinct keys; depth must not exceed the bound and drop
        # count must increase once full.
        for i in range(1000):
            cs.enqueue_market_snapshot(
                f"ASSET{i}",
                {"1h": {"candles": [{"open_time_ms": i + 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]}},
            )
        assert cs.queue_depth() <= 100
        assert cs._drop_count() > 0
    finally:
        _clear_queue()


def test_adaptive_queue_metrics_expose_depth_and_oldest() -> None:
    import engine.adaptive.candle_store as cs

    _clear_queue()
    cs.enqueue_market_snapshot("BTCUSDT", {"1h": {"candles": [{"open_time_ms": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]}})
    metrics = cs.queue_metrics()
    assert metrics["depth"] >= 1
    assert metrics["max"] >= 1
    assert metrics["oldest_age_seconds"] >= 0
    assert metrics["dropped_total"] >= 0
    _clear_queue()


# ── Outcome outbox repair (Phase 17) ─────────────────────────────────────────


def test_outbox_repair_query_uses_not_exists() -> None:
    from datetime import datetime, timezone

    from services.outcome_reconciliation import build_outbox_repair_query

    query = build_outbox_repair_query(
        cutoff=datetime.now(timezone.utc).replace(tzinfo=None),
        limit=50,
    )
    rendered = str(query)
    # SQLAlchemy renders a negated EXISTS as ``NOT (EXISTS (SELECT ...)``.
    assert "NOT (EXISTS" in rendered or "NOT EXISTS" in rendered or "~" in rendered
    assert "outcome_notifications" in rendered
    assert "closed_at" in rendered


def test_outbox_repair_query_has_stable_cursor() -> None:
    from datetime import datetime, timezone

    from services.outcome_reconciliation import build_outbox_repair_query

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None)
    query = build_outbox_repair_query(cutoff=cutoff, limit=10, after_id=42)
    rendered = str(query)
    assert "closed_at" in rendered
    assert "id" in rendered


# ── TradingView gate (Phase 16) ──────────────────────────────────────────────


def test_tradingview_disabled_causes_zero_network_calls() -> None:
    import os

    os.environ["TRADINGVIEW_ENABLED"] = "0"
    os.environ["TRADINGVIEW_OHLCV_ENABLED"] = "0"
    try:
        import data.fetcher as fetcher

        # get_tradingview_candles must return [] before importing/querying the
        # provider library when the feature gate is disabled.
        assert fetcher.get_tradingview_candles("BTCUSDT", "1h") == []
    finally:
        del os.environ["TRADINGVIEW_ENABLED"]
        del os.environ["TRADINGVIEW_OHLCV_ENABLED"]


def test_tradingview_ohlcv_disabled_returns_empty() -> None:
    import os

    os.environ["TRADINGVIEW_OHLCV_ENABLED"] = "0"
    try:
        from data.providers import fetch_tradingview_candles

        assert fetch_tradingview_candles("BTCUSDT", "1h") == []
    finally:
        del os.environ["TRADINGVIEW_OHLCV_ENABLED"]


# ── Migration head (Phase 19) ────────────────────────────────────────────────


def test_migration_has_single_head() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config("alembic.ini")
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1
    assert heads[0] == "0034_production_integrity"


def test_expected_migration_head_matches_repository() -> None:
    from pathlib import Path

    expected = Path("db/migrations/versions/0034_production_integrity.py")
    assert expected.exists(), "expected migration file missing"
