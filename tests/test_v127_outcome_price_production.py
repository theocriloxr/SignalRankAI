from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_outcome_queries_accept_historical_delivery_state_casing() -> None:
    source = (ROOT / "engine" / "realtime_outcome_tracker.py").read_text(encoding="utf-8")
    assert '_DELIVERY_PROOF_STATES = ("sent", "delivered", "confirmed", "reconciled")' in source
    assert "func.lower(SignalDelivery.delivery_state).in_(_DELIVERY_PROOF_STATES)" in source
    assert "SignalDelivery.delivery_confirmed_at.is_not(None)" not in source


def test_lifecycle_notifications_accept_sent_and_confirmed_proofs() -> None:
    source = (ROOT / "engine" / "signal_lifecycle.py").read_text(encoding="utf-8")
    assert 'func.lower(SignalDelivery.delivery_state).in_(("sent", "confirmed", "delivered", "reconciled"))' in source


@pytest.mark.asyncio
async def test_interactive_reconcile_uses_same_lifecycle_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.realtime_outcome_tracker as module

    signal = {"signal_id": "sig-1", "asset": "XAUTUSDT"}
    observation = module.OutcomePriceObservation(
        asset="XAUTUSDT",
        price=4083.0,
        provider="okx",
        quote_time="2026-07-30T00:00:00+00:00",
        provider_trusted=True,
    )
    calls: list[str] = []

    async def fake_fetch(signal_id: str):
        calls.append(f"fetch:{signal_id}")
        return signal

    async def fake_quote(asset: str):
        calls.append(f"quote:{asset}")
        return observation

    async def fake_check(payload, observation=None):
        assert payload is signal
        assert observation is not None and observation.price == 4083.0
        calls.append("check")

    async def fake_dispatch():
        calls.append("dispatch")

    monkeypatch.setattr(module, "_fetch_signal_for_reconciliation", fake_fetch)
    monkeypatch.setattr(module, "_get_outcome_quote", fake_quote)
    monkeypatch.setattr(module.outcome_tracker, "_check_signal", fake_check)
    monkeypatch.setattr(module.outcome_tracker, "_dispatch_pending_notifications", fake_dispatch)

    assert await module.reconcile_signal_now("sig-1") is True
    assert calls == ["fetch:sig-1", "quote:XAUTUSDT", "check", "dispatch"]


def test_monitor_and_check_outcome_are_read_through_and_use_typed_quotes() -> None:
    source = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    monitor_start = source.index("async def _build_monitor_snapshot")
    monitor_end = source.index("def _parse_tp_levels_for_outcome", monitor_start)
    monitor_source = source[monitor_start:monitor_end]
    assert "get_live_price_result" in monitor_source
    assert "validate_quote_for_final_delivery" in monitor_source
    assert "from core.trade_tracker" not in monitor_source
    assert "Price feed:" in monitor_source
    assert "result.provider_symbol" in monitor_source
    assert "feed_identity" in monitor_source

    callback_start = source.index("async def _check_outcome_callback")
    callback_end = source.index("application.add_handler(_CQH(_check_outcome_callback", callback_start)
    callback_source = source[callback_start:callback_end]
    assert "reconcile_signal_now" in callback_source
    assert "CHECK_OUTCOME_RECONCILE_TIMEOUT_SECONDS" in callback_source
    assert "_snapshot.is_stale" in callback_source


def test_stale_redis_ticks_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    import core.trade_tracker as tracker

    stale = {
        "price": 4074.0,
        "source": "okx",
        "updated_at": time.time() - 120.0,
        "event_time_ms": int((time.time() - 120.0) * 1000),
    }
    fresh = {
        "price": 4083.0,
        "source": "okx",
        "updated_at": time.time(),
        "event_time_ms": int(time.time() * 1000),
    }

    monkeypatch.setenv("TRADE_TRACKER_LATEST_TICK_MAX_AGE_SECONDS", "15")
    monkeypatch.setattr(tracker.state, "get_latest_tick_sync", lambda _symbol: stale)
    assert tracker._latest_tick_price("XAUTUSDT") is None

    monkeypatch.setattr(tracker.state, "get_latest_tick_sync", lambda _symbol: fresh)
    assert tracker._latest_tick_price("XAUTUSDT") == pytest.approx(4083.0)


def test_adaptive_candle_persistence_uses_bulk_upsert_and_delta_queue() -> None:
    source = (ROOT / "engine" / "adaptive" / "candle_store.py").read_text(encoding="utf-8")
    assert "insert as pg_insert" in source
    assert "on_conflict_do_update" in source
    assert 'constraint="uq_market_candles_symbol_tf_open"' in source
    assert "ADAPTIVE_CANDLE_UPSERT_CHUNK_SIZE" in source
    assert "ADAPTIVE_CANDLE_OPEN_UPDATE_INTERVAL_SECONDS" in source
    assert "rows_to_queue" in source


def test_production_profile_has_no_duplicates_and_freshness_guards() -> None:
    path = ROOT / "SignalRankAI_v1.3.2_Railway_Production_Launch.env.example"
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    keys = [line.split("=", 1)[0] for line in lines if line and not line.startswith("#") and "=" in line]
    assert len(keys) == len(set(keys))
    assert "APP_VERSION=1.3.2" in lines
    assert "OUTCOME_TRACKER_DB_PRIORITY=critical" in lines
    assert "OUTCOME_DB_ADMISSION_TIMEOUT_SECONDS=12" in lines
    assert "TRADE_TRACKER_LATEST_TICK_MAX_AGE_SECONDS=15" in lines
    assert "PAYMENTS_PUBLIC_ENABLED=1" in lines
    assert "REAL_EXECUTION_ENABLED=0" in lines


def test_adaptive_status_uses_typed_nullable_asset_bind() -> None:
    source = (ROOT / "signalrank_telegram" / "adaptive_commands.py").read_text(encoding="utf-8")
    assert 'bindparam("asset", type_=String())' in source
    assert "WHERE (:asset IS NULL OR asset=:asset)" in source


def test_command_error_classifier_separates_sql_defects_from_pressure() -> None:
    from signalrank_telegram.error_classification import classify_command_exception

    assert classify_command_exception(Exception("asyncpg.exceptions.AmbiguousParameterError: could not determine data type")) == "db_query"
    assert classify_command_exception(Exception("too many clients already")) == "db_pressure"
    assert classify_command_exception(Exception("unexpected application error")) == "other"


def test_ops_health_uses_valid_redis_timeout_and_proof_backed_filter() -> None:
    source = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    start = source.index("async def ops_health_command")
    end = source.index("async def notify_command", start)
    block = source[start:end]
    assert "socket_timeout=3" in block
    assert "socket_timeout_seconds" not in block
    assert 'os.getenv("STATE_REDIS_URL") or os.getenv("REDIS_URL")' in block
    assert "SignalDelivery.sent_ok.is_(True)" in block
    assert "SignalDelivery.telegram_message_id.is_not(None)" in block
    assert "collect_database_health" in block


def test_simulation_uses_terminal_outcomes_and_reports_backlog() -> None:
    service = (ROOT / "core" / "paper_trading_service.py").read_text(encoding="utf-8")
    assert 'terminal_statuses = (' in service
    assert 'partial_statuses = ("tp1", "tp2")' in service
    assert '"pending_delivered": max(0, delivered_total - terminal_count)' in service
    commands = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    assert "Completed delivered outcomes available" in commands
    assert "Still awaiting a terminal outcome" in commands


def test_production_profile_uses_one_primary_with_reviewed_pool_headroom() -> None:
    lines = (ROOT / "SignalRankAI_v1.3.2_Railway_Production_Launch.env.example").read_text(encoding="utf-8")
    assert "DB_POOL_SIZE=2" in lines
    assert "DB_MAX_OVERFLOW=0" in lines
    assert "DB_POOL_RAILWAY_ABSOLUTE_CAP=2" in lines
    assert "DB_MAX_OVERFLOW_RAILWAY_ABSOLUTE_CAP=0" in lines
    assert "DB_PRODUCTION_CONNECTION_RESERVE=5" in lines
    diagnostics = (ROOT / "scripts" / "deployment_diagnostics.py").read_text(encoding="utf-8")
    assert 'name="postgresql_capacity_headroom"' in diagnostics
    assert "Do not add a second writable primary" in diagnostics



def test_webhook_timeout_is_retryable_without_dual_queue_fallback() -> None:
    source = (ROOT / "railway_main.py").read_text(encoding="utf-8")
    assert "redis_enqueue_indeterminate" in source
    assert "action=retry_no_local_fallback" in source
    assert 'if error in {"queue_full", "redis_enqueue_indeterminate"}' in source
    timeout_index = source.index("except asyncio.TimeoutError:", source.index("async def _telegram_webhook_route"))
    indeterminate_index = source.index("if redis_enqueue_indeterminate:", timeout_index)
    fallback_index = source.index("redis enqueue failed — falling back to in-process queue", indeterminate_index)
    assert timeout_index < indeterminate_index < fallback_index

def test_version_fingerprint() -> None:
    from core.version import APP_VERSION, RELEASE_FINGERPRINT

    assert APP_VERSION == "1.3.6.7"
    assert RELEASE_FINGERPRINT == "v1.3.6.7-integrity-accounting-dedup-hotfix-20260802"
