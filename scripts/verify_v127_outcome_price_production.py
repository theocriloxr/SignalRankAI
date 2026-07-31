"""Static verifier for SignalRankAI v1.2.7 outcome/price/production release."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def require(condition: bool, label: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL {label}")
    print(f"PASS {label}")


def main() -> None:
    from core.version import APP_VERSION, RELEASE_FINGERPRINT

    require(APP_VERSION == "1.3.2", "runtime version")
    require(
        RELEASE_FINGERPRINT == "v1.3.2-auto-delivery-callback-monitor-recovery-20260730",
        "release fingerprint",
    )

    tracker = (ROOT / "engine/realtime_outcome_tracker.py").read_text(encoding="utf-8")
    require("func.lower(SignalDelivery.delivery_state).in_(_DELIVERY_PROOF_STATES)" in tracker, "case-normalised delivery proof")
    require("async def reconcile_signal_now" in tracker, "interactive outcome reconciliation")
    require("reconciliation_backfill fetched=%d" in tracker, "backfill observability")
    require("priority=_outcome_db_priority()" in tracker, "critical outcome DB lane")

    lifecycle = (ROOT / "engine/signal_lifecycle.py").read_text(encoding="utf-8")
    require('("sent", "confirmed", "delivered", "reconciled")' in lifecycle, "notification recipient state contract")

    bot = (ROOT / "signalrank_telegram/bot.py").read_text(encoding="utf-8")
    require("get_live_price_result" in bot and "validate_quote_for_final_delivery" in bot, "typed monitor quote")
    require("MONITOR_SNAPSHOT_MAX_AGE_SECONDS" in bot, "monitor freshness ceiling")
    require("result.provider_symbol" in bot and "feed_identity" in bot, "monitor provider symbol attribution")
    require("CHECK_OUTCOME_RECONCILE_TIMEOUT_SECONDS" in bot, "check-outcome read-through reconciliation")
    require("from core.trade_tracker" not in bot[bot.index("async def _build_monitor_snapshot"):bot.index("async def _build_monitor_snapshot") + 9000], "monitor avoids legacy price cache")

    trade_tracker = (ROOT / "core/trade_tracker.py").read_text(encoding="utf-8")
    require("TRADE_TRACKER_LATEST_TICK_MAX_AGE_SECONDS" in trade_tracker, "stale Redis tick rejection")

    candle_store = (ROOT / "engine/adaptive/candle_store.py").read_text(encoding="utf-8")
    require("pg_insert" in candle_store and "on_conflict_do_update" in candle_store, "bulk adaptive candle upsert")
    require("ADAPTIVE_CANDLE_OPEN_UPDATE_INTERVAL_SECONDS" in candle_store, "adaptive candle delta capture")

    adaptive_commands = (ROOT / "signalrank_telegram/adaptive_commands.py").read_text(encoding="utf-8")
    require('bindparam("asset", type_=String())' in adaptive_commands, "typed adaptive status bind")

    error_classification = (ROOT / "signalrank_telegram/error_classification.py").read_text(encoding="utf-8")
    require("ambiguousparametererror" in error_classification.lower() and "db_query" in error_classification, "SQL defects not labelled DB pressure")

    commands = (ROOT / "signalrank_telegram/commands.py").read_text(encoding="utf-8")
    require("socket_timeout=3" in commands and "socket_timeout_seconds" not in commands, "valid Redis health timeout")
    require("Completed delivered outcomes available" in commands, "transparent simulation evidence")

    runtime = (ROOT / "runtime_safety.py").read_text(encoding="utf-8")
    require("_clean_paystack_key" in runtime, "Paystack key normalisation")

    readiness = (ROOT / "scripts/production_readiness_check.py").read_text(encoding="utf-8")
    require('"/metrics/prometheus"' in readiness, "metrics readiness route marker")

    production = ROOT / "SignalRankAI_v1.3.2_Railway_Production_Launch.env.example"
    staging = ROOT / "SignalRankAI_v1.3.2_Railway_Full_System_Live_Paystack_Staging.env.example"
    require(production.exists(), "production environment profile")
    require(staging.exists(), "staging environment profile")
    profile = production.read_text(encoding="utf-8")
    require("APP_ENV=production" in profile, "production mode")
    require("REAL_EXECUTION_ENABLED=0" in profile and "COPY_TRADE_ENABLED=0" in profile, "initial live-execution fail-closed")
    require("PAYMENTS_PUBLIC_ENABLED=1" in profile and "REAL_PAYOUTS_ENABLED=0" in profile, "public payments with payouts fail-closed")
    require("DB_POOL_SIZE=2" in profile and "DB_MAX_OVERFLOW=0" in profile, "safe Railway monolith app pool")

    diagnostics = (ROOT / "scripts/deployment_diagnostics.py").read_text(encoding="utf-8")
    require('name="postgresql_capacity_headroom"' in diagnostics, "PostgreSQL capacity launch gate")

    railway = (ROOT / "railway_main.py").read_text(encoding="utf-8")
    require("redis_enqueue_indeterminate" in railway and "retry_no_local_fallback" in railway, "webhook timeout duplicate prevention")

    print("PASS v1.2.7 outcome/price/production verification")


if __name__ == "__main__":
    main()
