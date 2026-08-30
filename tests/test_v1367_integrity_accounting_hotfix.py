from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from core.outcome_ordering import evaluate_outcome_delivery, outcome_is_terminal
from core.partial_exit_accounting import calculate_partial_exit_result
from core.production_integrity import signal_thesis_fingerprint
from services.performance_ledger import PERFORMANCE_POLICY_VERSION, _classify


ROOT = Path(__file__).resolve().parents[1]


def _signal(**overrides):
    payload = {
        "asset": "BTCUSDT",
        "direction": "SELL",
        "strategy_name": "EMA Trend",
        "regime": "trend",
        "timeframe": "15m",
        "entry": 100.0,
        "stop_loss": 101.0,
        "take_profit": [98.8, 98.2, 97.2],
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_weighted_partial_exit_r_for_tp1_and_tp2(monkeypatch) -> None:
    monkeypatch.delenv("SIGNAL_TP1_CLOSE_FRACTION", raising=False)
    monkeypatch.delenv("SIGNAL_TP2_CLOSE_FRACTION", raising=False)
    tp1 = calculate_partial_exit_result(
        entry=100,
        stop_loss=101,
        take_profit=[98.8, 98.2, 97.2],
        direction="SELL",
        highest_tp=1,
    )
    tp2 = calculate_partial_exit_result(
        entry=100,
        stop_loss=101,
        take_profit=[98.8, 98.2, 97.2],
        direction="SELL",
        highest_tp=2,
    )
    assert tp1 is not None and tp1.realized_r == 0.6
    assert tp2 is not None and tp2.realized_r == 1.05
    assert tp1.policy_version == "partial-exit-weighted-v2"


def test_performance_classifier_populates_stopped_tp_buckets() -> None:
    signal = _signal()
    tp1 = _classify(
        signal=signal,
        outcome=SimpleNamespace(
            status="partial_win_be",
            canonical_outcome="partial_win",
            r_multiple=-1.0,
            meta={"tp_hit_index": 1},
        ),
        lifecycle=SimpleNamespace(highest_tp_hit=1),
        monitoring=None,
    )
    tp2 = _classify(
        signal=signal,
        outcome=SimpleNamespace(
            status="partial_win_be",
            canonical_outcome="partial_win",
            r_multiple=-1.0,
            meta={"tp_hit_index": 2},
        ),
        lifecycle=SimpleNamespace(highest_tp_hit=2),
        monitoring=None,
    )
    assert tp1[:4] == ("STOPPED_AT_TP1", Decimal("0.6"), "lifecycle_partial_exit", True)
    assert tp2[:4] == ("STOPPED_AT_TP2", Decimal("1.05"), "lifecycle_partial_exit", True)


def test_thesis_fingerprint_ignores_hidden_regime_and_timeframe_by_default(monkeypatch) -> None:
    monkeypatch.delenv("THESIS_FINGERPRINT_INCLUDE_REGIME", raising=False)
    monkeypatch.delenv("THESIS_FINGERPRINT_INCLUDE_TIMEFRAME", raising=False)
    first = signal_thesis_fingerprint({
        "asset": "BNBUSDT", "direction": "BUY", "strategy_name": "EMA Trend",
        "regime": "trend", "timeframe": "5m", "entry": 587.37,
    })
    second = signal_thesis_fingerprint({
        "asset": "BNBUSDT", "direction": "BUY", "strategy_name": "EMA Trend",
        "regime": "range", "timeframe": "1h", "entry": 587.34,
    })
    assert first == second


def test_partial_win_be_is_terminal_and_blocks_later_alerts() -> None:
    assert outcome_is_terminal("partial_win_be") is True
    decision = evaluate_outcome_delivery(
        "sl",
        highest_delivered_rank=25,
        terminal_already_delivered=True,
    )
    assert decision.allowed is False
    assert decision.reason == "terminal_already_delivered"


def test_product_delivery_has_no_owner_or_diagnostic_dedup_bypass() -> None:
    pg_source = (ROOT / "db" / "pg_features.py").read_text(encoding="utf-8")
    bot_source = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    assert "OWNER_ADMIN_BYPASS_DELIVERY_DEDUPE" not in pg_source
    assert "DIAGNOSTIC_DELIVERY_BYPASS" not in bot_source
    assert "semantic thesis reused" in pg_source
    assert "suppressed duplicate thesis recipient" in pg_source
    assert "asset_delivery_locked" in bot_source


def test_terminal_notifications_are_traceable_and_not_recipient_sleep_bound() -> None:
    source = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    assert "Signal ID: <code>{ref}</code>" in source
    assert "Historical reconciliation:" in source
    assert "Outcome time:" in source
    assert "Notification time:" in source
    start = source.index("    def _send_outcome_notifications_owned():")
    end = source.index("    def send_outcome_notifications():", start)
    notification_source = source[start:end]
    assert "asyncio.sleep(0.5)" not in notification_source
    assert "quiet_deferred_count == 0 and failed_count == 0" in notification_source
    assert "Parse the outcome stage once per outcome" in notification_source


def test_worker_runs_partial_exit_repair_before_ledger_reconciliation() -> None:
    source = (ROOT / "worker" / "worker.py").read_text(encoding="utf-8")
    repair = source.index("repair_partial_exit_outcomes")
    reconcile = source.index("reconcile_all_performance_ledgers", repair)
    assert repair < reconcile


def test_performance_policy_migrates_old_rows_and_excludes_duplicate_theses() -> None:
    source = (ROOT / "services" / "performance_ledger.py").read_text(encoding="utf-8")
    assert PERFORMANCE_POLICY_VERSION == "proof-ledger-v2-partial-exit"
    assert '"DUPLICATE_EXCLUDED"' in source
    assert '"duplicate_deliveries_excluded"' in source
    assert "v1.3.6.7_partial_exit_accounting" in source


def test_paper_close_all_has_explicit_fresh_mark_recovery() -> None:
    service = (ROOT / "core" / "paper_trading_service.py").read_text(encoding="utf-8")
    commands = (ROOT / "signalrank_telegram" / "extended_commands.py").read_text(encoding="utf-8")
    assert "allow_last_mark_fallback" in service
    assert "PAPER_CLOSE_ALL_LAST_MARK_MAX_AGE_SECONDS" in service
    assert "/paper_close_all FORCE CONFIRM" in commands


def test_legacy_sl_with_breakeven_lifecycle_is_classified_as_partial_exit() -> None:
    signal = _signal()
    classified = _classify(
        signal=signal,
        outcome=SimpleNamespace(
            status="sl",
            canonical_outcome="loss",
            r_multiple=-1.0,
            meta={"tp_hit_index": 1},
        ),
        lifecycle=SimpleNamespace(
            highest_tp_hit=1,
            terminal_event_type="breakeven_stop",
        ),
        monitoring=None,
    )
    assert classified[:4] == (
        "STOPPED_AT_TP1",
        Decimal("0.6"),
        "lifecycle_partial_exit",
        True,
    )


def test_semantic_entry_comparison_handles_log_bucket_boundaries() -> None:
    from core.production_integrity import semantic_entries_equivalent, signal_thesis_scope

    assert semantic_entries_equivalent(587.37, 587.34)
    assert not semantic_entries_equivalent(587.37, 590.0)
    assert signal_thesis_scope({
        "asset": "bnbusdt",
        "direction": "BUY",
        "strategy_name": " EMA   Trend ",
    }) == "BNBUSDT|long|ema trend"


def test_owner_tier_cannot_silently_reduce_global_asset_cooldown(monkeypatch) -> None:
    from services.asset_repeat_policy import get_asset_repeat_lock_hours

    monkeypatch.setenv("ASSET_REPEAT_LOCK_HOURS", "4")
    monkeypatch.setenv("VIP_ASSET_COOLDOWN_HOURS", "0")
    monkeypatch.delenv("ALLOW_TIER_ASSET_COOLDOWN_OVERRIDES", raising=False)
    assert get_asset_repeat_lock_hours("owner") == 4.0
    monkeypatch.setenv("ALLOW_TIER_ASSET_COOLDOWN_OVERRIDES", "1")
    monkeypatch.delenv("ALLOW_ASSET_COOLDOWN_REDUCTION", raising=False)
    assert get_asset_repeat_lock_hours("owner") == 4.0


def test_partial_exit_is_terminal_in_database_outcome_projection() -> None:
    source = (ROOT / "db" / "pg_features.py").read_text(encoding="utf-8")
    section = source[source.index("async def upsert_outcome"):source.index("async def queue_outcome_notifications_for_outcome")]
    assert '"partial_win_be"' in section
    assert '"partial_win"' in section


def test_asset_cooldown_stays_active_when_legacy_exact_dedupe_is_disabled() -> None:
    source = (ROOT / "db" / "pg_features.py").read_text(encoding="utf-8")
    section = source[source.index("async def record_signal_delivery"):source.index("async def mark_signal_delivery_result")]
    assert "if cutoff is not None:" in section
    assert section.index("get_asset_repeat_lock_hours") < section.index("if cutoff is not None:")
    assert "user-asset delivery lock unavailable; blocking" in section


def test_historical_repair_includes_legacy_sl_breakeven_events() -> None:
    source = (ROOT / "services" / "performance_ledger.py").read_text(encoding="utf-8")
    repair = source[source.index("async def repair_partial_exit_outcomes"):source.index("async def reconcile_user_performance_ledger")]
    assert 'func.lower(SignalLifecycle.terminal_event_type) == "breakeven_stop"' in repair
    assert 'outcome.status = "partial_win_be"' in repair


def test_notification_quiet_all_day_remains_pending_and_lease_exceeds_budget() -> None:
    source = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    section = source[source.index("def _send_outcome_notifications_owned"):source.index("def smart_exit_guard_job")]
    assert "# Quiet all day: keep the durable notification pending." in section
    assert "quiet_deferred_count += 1" in section
    assert "lease_seconds = max(60, configured_budget + 30" in section
    assert section.count("Final outcome: <b>Stop Loss before TP1</b>") == 1


def test_performance_reply_uses_canonical_partial_and_duplicate_buckets() -> None:
    source = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    assert "Stopped TP1 / TP2:" in source
    assert "STOPPED_AT_TP1" in source
    assert "STOPPED_AT_TP2" in source
    assert "Duplicate thesis deliveries excluded:" in source
