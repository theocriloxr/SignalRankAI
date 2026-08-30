from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(name: str, condition: bool) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {name}")
    print(f"PASS: {name}")


def main() -> None:
    ledger = (ROOT / "services/performance_ledger.py").read_text("utf-8")
    worker = (ROOT / "worker/worker.py").read_text("utf-8")
    bot = (ROOT / "signalrank_telegram/bot.py").read_text("utf-8")
    version = (ROOT / "core/version.py").read_text("utf-8")
    check("v1.3.6.8 foundations retained", 'CODE_VERSION = "1.3.6.9"' in version and (ROOT / "core/durable_event_stream.py").exists())
    check("per-user savepoint", "async with session.begin_nested()" in ledger)
    check("cursor pagination", "User.id > int(after_user_id)" in ledger)
    check("audited policy migration", "performance-policy-migration-v1" in ledger)
    check("grouped failures", "failed_users_by_reason" in ledger)
    check("delivery proof fallback", "getattr(delivery, \"delivered_at_utc\", None)" in ledger and 'missing_delivery_timestamp' in ledger)
    check("retry queue", "performance_reconciliation:retry" in ledger)
    check("dead-letter queue", "performance_reconciliation:dlq" in ledger)
    check("post-commit checkpoint", "persist_performance_reconciliation_result" in ledger)
    check("distinct delivery scope", "select(SignalDelivery.user_id, SignalDelivery.signal_id)" in ledger)
    check("outcome-ledger mismatch gate", "outcome_to_ledger_mismatch" in ledger and "mismatch_count == 0" in ledger)
    check("commit before certification failure", worker.index("await session.commit()") < worker.index("performance_result.certification_failed"))
    check("owner rebuild command", 'CommandHandler("performance_rebuild"' in bot)
    check("owner audit command", 'CommandHandler("performance_audit"' in bot)
    check("event stream disabled by default", 'DURABLE_EVENT_STREAM_ENABLED", "0"' in (ROOT / "core/durable_event_stream.py").read_text("utf-8"))
    print("v1.3.6.8 foundation verification complete on current release")


if __name__ == "__main__":
    main()
