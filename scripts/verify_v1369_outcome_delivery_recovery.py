from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(name: str, condition: bool) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {name}")
    print(f"PASS: {name}")


def main() -> None:
    pg = (ROOT / "db/pg_features.py").read_text("utf-8")
    tracker = (ROOT / "engine/realtime_outcome_tracker.py").read_text("utf-8")
    reconciliation = (ROOT / "services/outcome_reconciliation.py").read_text("utf-8")
    worker = (ROOT / "worker/worker.py").read_text("utf-8")
    bot = (ROOT / "signalrank_telegram/bot.py").read_text("utf-8")
    owner = (ROOT / "signalrank_telegram/owner_commands.py").read_text("utf-8")
    version = (ROOT / "core/version.py").read_text("utf-8")

    check("version", 'CODE_VERSION = "1.3.6.9"' in version)
    check("release fingerprint", "outcome-delivery-recovery-hotfix" in version)
    check("missing env helper restored", "def _env_bool(" in pg)
    check("recipient suppression flag guarded", "OUTCOME_DUPLICATE_NOTIFICATION_SUPPRESSION_ENABLED" in pg)
    check("persistence traceback", "persist_outcome error signal=%s status=%s" in tracker and "logger.exception(" in tracker)
    outcome_commit = tracker.index("# Commit canonical trading truth before notification fan-out")
    outbox_queue = tracker.index("queue_outcome_notifications_for_outcome", outcome_commit)
    first_commit = tracker.index("await session.commit()", outcome_commit)
    check("outcome committed before outbox", first_commit < outbox_queue and "outbox queue failed after outcome commit" in tracker)
    check("stale outcome reconciliation", "lifecycle/outcome disagreements" in reconciliation)
    check("per-signal savepoint", reconciliation.count("async with session.begin_nested()") >= 2)
    check("human correction protection", "human_corrected" in reconciliation)
    check("audited system correction", "system:v1.3.6.9-outcome-reconciliation" in reconciliation)
    check("outbox repair", "repair_outcome_notification_outbox" in reconciliation and "outbox_repair.as_dict()" in worker)
    check("terminal message coverage", all(token in bot for token in ("Signal Window Closed", "Entry Not Triggered", "Signal Invalidated", "Protected Exit")))
    check("notification cycle telemetry", "[outcome_notify_cycle]" in bot)
    check("resend budget backoff", "resend:budget_backoff_until" in bot and "RESEND_BUDGET_BACKOFF_SECONDS" in bot)
    check("owner outcome rebuild", "async def outcome_rebuild_command" in owner and 'CommandHandler("outcome_rebuild"' in bot)
    check("owner outcome audit", "async def outcome_audit_command" in owner and 'CommandHandler("outcome_audit"' in bot)
    print("v1.3.6.9 static verification complete")


if __name__ == "__main__":
    main()
