#!/usr/bin/env python3
"""Deterministic verifier for SignalRankAI v1.3.6.7 integrity accounting."""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def check(label: str, condition: bool) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {label}")
    print(f"PASS: {label}")


def source(path: str) -> str:
    value = (ROOT / path).read_text(encoding="utf-8")
    ast.parse(value, filename=path)
    return value


def main() -> int:
    os.environ.setdefault("THESIS_FINGERPRINT_INCLUDE_REGIME", "0")
    os.environ.setdefault("THESIS_FINGERPRINT_INCLUDE_TIMEFRAME", "0")
    os.environ.setdefault("SIGNAL_TP1_CLOSE_FRACTION", "0.50")
    os.environ.setdefault("SIGNAL_TP2_CLOSE_FRACTION", "0.25")

    from core.version import APP_VERSION, RELEASE_FINGERPRINT
    from core.partial_exit_accounting import calculate_partial_exit_result
    from core.production_integrity import canonical_direction, semantic_entries_equivalent, signal_thesis_fingerprint, signal_thesis_scope
    from core.outcome_ordering import outcome_is_terminal
    from services.performance_ledger import PERFORMANCE_POLICY_VERSION, _classify

    check("release version", APP_VERSION == "1.3.6.7")
    check(
        "release fingerprint",
        RELEASE_FINGERPRINT == "v1.3.6.7-integrity-accounting-dedup-hotfix-20260802",
    )
    check(
        "migration head retained",
        (ROOT / "db/migrations/versions/0034_production_integrity.py").exists(),
    )

    tp1 = calculate_partial_exit_result(
        entry=100, stop_loss=101, take_profit=[98.8, 98.2, 97.2],
        direction="SELL", highest_tp=1,
    )
    tp2 = calculate_partial_exit_result(
        entry=100, stop_loss=101, take_profit=[98.8, 98.2, 97.2],
        direction="SELL", highest_tp=2,
    )
    check("TP1 protected exit weighted R", tp1 is not None and tp1.realized_r == 0.6)
    check("TP2 protected exit weighted R", tp2 is not None and tp2.realized_r == 1.05)

    signal = SimpleNamespace(
        asset="BTCUSDT", direction="SELL", strategy_name="EMA Trend",
        regime="trend", timeframe="15m", entry=100.0, stop_loss=101.0,
        take_profit=[98.8, 98.2, 97.2],
    )
    bucket1 = _classify(
        signal=signal,
        outcome=SimpleNamespace(
            status="partial_win_be", canonical_outcome="partial_win",
            r_multiple=-1.0, meta={"tp_hit_index": 1},
        ),
        lifecycle=SimpleNamespace(highest_tp_hit=1), monitoring=None,
    )
    bucket2 = _classify(
        signal=signal,
        outcome=SimpleNamespace(
            status="partial_win_be", canonical_outcome="partial_win",
            r_multiple=-1.0, meta={"tp_hit_index": 2},
        ),
        lifecycle=SimpleNamespace(highest_tp_hit=2), monitoring=None,
    )
    check("performance TP1-stopped bucket", bucket1[0] == "STOPPED_AT_TP1" and float(bucket1[1]) == 0.6)
    check("performance TP2-stopped bucket", bucket2[0] == "STOPPED_AT_TP2" and float(bucket2[1]) == 1.05)
    check("performance policy migration", PERFORMANCE_POLICY_VERSION == "proof-ledger-v2-partial-exit")

    fp_a = signal_thesis_fingerprint({
        "asset": "BNBUSDT", "direction": "BUY", "strategy_name": "EMA Trend",
        "regime": "trend", "timeframe": "5m", "entry": 587.37,
    })
    fp_b = signal_thesis_fingerprint({
        "asset": "BNBUSDT", "direction": "LONG", "strategy_name": "EMA Trend",
        "regime": "range", "timeframe": "1h", "entry": 587.34,
    })
    check("semantic thesis collapse", fp_a == fp_b)
    check("protected exit terminal ordering", outcome_is_terminal("partial_win_be") and outcome_is_terminal("partial_win"))
    check("direction aliases canonicalized", canonical_direction("BUY") == "long" and canonical_direction("SELL") == "short")
    check("semantic near-entry comparison", semantic_entries_equivalent(587.37, 587.34))
    check("semantic scope stable", signal_thesis_scope({"asset": "bnbusdt", "direction": "BUY", "strategy_name": " EMA   Trend "}) == "BNBUSDT|long|ema trend")

    pg = source("db/pg_features.py")
    repository = source("db/repository.py")
    bot = source("signalrank_telegram/bot.py")
    tracker = source("engine/realtime_outcome_tracker.py")
    ledger = source("services/performance_ledger.py")
    worker = source("worker/worker.py")
    paper = source("core/paper_trading_service.py")
    commands = source("signalrank_telegram/extended_commands.py")
    repair = source("scripts/repair_active_signal_duplicates.py")

    check("owner delivery dedup bypass removed", "OWNER_ADMIN_BYPASS_DELIVERY_DEDUPE" not in pg)
    check("diagnostic asset-lock bypass removed", "DIAGNOSTIC_DELIVERY_BYPASS" not in bot)
    check("atomic semantic admission in primary path", "semantic thesis reused" in pg)
    check("atomic semantic admission in repository path", "signal-thesis:" in repository and "canonical_direction" in repository)
    check("asset cooldown independent of exact-id cutoff", pg.index("get_asset_repeat_lock_hours") < pg.index("if cutoff is not None:"))
    check("partial outcomes immutable in DB", "partial_win_be" in pg[pg.index("async def upsert_outcome"):pg.index("async def queue_outcome_notifications_for_outcome")])
    check("legacy duplicate outcome suppression", "suppressed duplicate thesis recipient" in pg)
    check("partial outcome historical repair", "repair_partial_exit_outcomes" in ledger and "v1.3.6.7_partial_exit_accounting" in ledger)
    check("partial outcome worker integration", worker.index("repaired_partial_exits = await repair_partial_exit_outcomes") < worker.index("performance_result = await reconcile_all_performance_ledgers"))
    check("tracker persists weighted partial exit", "partial_exit_realized_r" in tracker)
    check("duplicate deliveries excluded from claims", "DUPLICATE_EXCLUDED" in ledger)
    check("terminal messages identify signal", "Signal ID: <code>{ref}</code>" in bot)
    check("terminal messages identify historical replay", "Historical reconciliation:" in bot)
    check("successful outcome globally finalized", "quiet_deferred_count == 0 and failed_count == 0" in bot)
    check("paper forced recovery uses fresh mark", "allow_last_mark_fallback" in paper and "PAPER_CLOSE_ALL_LAST_MARK_MAX_AGE_SECONDS" in paper)
    check("paper force command explicit", "/paper_close_all FORCE CONFIRM" in commands)
    check("legacy duplicate repair is non-destructive", "rows_deleted\": 0" in repair and "superseded_duplicate" in repair)

    print("overall=PASS release=v1.3.6.7 live_activation=BLOCKED_UNTIL_RUNTIME_CERTIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
