#!/usr/bin/env python3
"""Reconcile signal lifecycle records that may be in an inconsistent state.

This script identifies:
  - Signals marked "open" / "active" that have no delivery proof
  - Signals in WATCHING_FOR_ENTRY or ACTIVE_TRADE state without valid delivery
  - Legacy records that may contaminate live performance statistics

Usage:
  python scripts/reconcile_signal_lifecycle.py                  # dry-run
  python scripts/reconcile_signal_lifecycle.py --apply           # apply fixes
  python scripts/reconcile_signal_lifecycle.py --asset BTCUSDT   # specific asset
  python scripts/reconcile_signal_lifecycle.py --status open     # filter by status

Safe defaults:
  - Dry-run mode (no DB mutations) unless --apply is passed
  - Creates audit lifecycle events for every change
  - Never touches payment or real execution data
  - Never deletes records — only marks them with new provenance
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Ensure project root is on sys.path
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_THIS_DIR, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

os.environ.setdefault("PUBLIC_TESTING_MODE", "1")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def classify_signal(signal: dict[str, Any]) -> str:
    """Classify a signal's delivery-provenance health."""
    signal_id = str(signal.get("signal_id") or signal.get("id") or "")
    status = str(signal.get("status") or "").upper().strip()
    delivery_state = str(signal.get("delivery_state") or "").upper().strip()
    lifecycle_state = str(signal.get("lifecycle_state") or "").upper().strip()
    sent_ok = bool(signal.get("sent_ok") or False)
    has_delivery_proof = bool(
        signal.get("delivery_proof_id")
        or signal.get("proof_id")
        or signal.get("proof_ok")
        or sent_ok
    )

    if not signal_id:
        return "skip_no_id"

    # Already terminal — no action needed
    if lifecycle_state in ("EXPIRED", "MISSED_ENTRY", "SL_HIT", "TP1_HIT", "TP2_HIT", "TP3_HIT", "BREAKEVEN_STOP"):
        return "already_terminal"

    # Has delivery proof — should be in a delivery-progressed state
    if has_delivery_proof:
        return "has_proof_ok"

    # No delivery proof but claims to be delivered
    if delivery_state in ("CONFIRMED", "DELIVERED", "RECONCILED") and not has_delivery_proof:
        return "claimed_delivery_no_proof"

    # Active trade without delivery proof — most dangerous case
    if status in ("ACTIVE", "OPEN") or lifecycle_state == "ACTIVE_TRADE":
        if not has_delivery_proof:
            return "active_no_proof"
        return "active_with_proof"

    # Watching for entry without delivery proof
    if lifecycle_state == "WATCHING_FOR_ENTRY":
        if not has_delivery_proof:
            return "watching_no_proof"
        return "watching_with_proof"

    # Stored but not progressing
    if status in ("STORED", "NEW", "CANDIDATE", "VALIDATED") and not has_delivery_proof:
        return "stored_no_progress"

    return "other"


def reconcile_action(classification: str) -> tuple[str, str, str]:
    """Return (new_status, new_lifecycle_state, reason) for a classification."""
    actions = {
        "active_no_proof": (
            "RECONCILED",
            "EXPIRED",
            "legacy_reconciled:active_trade_without_delivery_proof",
        ),
        "claimed_delivery_no_proof": (
            "RECONCILED",
            "EXPIRED",
            "legacy_reconciled:claimed_delivery_without_proof",
        ),
        "watching_no_proof": (
            "RECONCILED",
            "EXPIRED",
            "legacy_reconciled:watching_for_entry_without_delivery_proof",
        ),
        "stored_no_progress": (
            "RECONCILED",
            "EXPIRED",
            "legacy_reconciled:stored_signal_no_delivery_progress",
        ),
    }
    return actions.get(classification, ("", "", ""))


def display_row(record: dict[str, Any]) -> str:
    """Format one record as a readable row."""
    signal_id = str(record.get("signal_id") or record.get("id") or "?").split("-")[0][:12]
    asset = str(record.get("asset") or "?")
    tf = str(record.get("timeframe") or "?")
    direction = str(record.get("direction") or "?")
    status = str(record.get("status") or "?")
    lifecycle = str(record.get("lifecycle_state") or "?")
    delivery = str(record.get("delivery_state") or "?")
    proof = "Y" if bool(record.get("sent_ok") or record.get("proof_ok") or record.get("delivery_proof_id")) else "N"
    created = str(record.get("created_at") or "")[:19]
    return (
        f"{signal_id:<14} {asset:<12} {tf:<6} {direction:<7} "
        f"{status:<12} {lifecycle:<20} {delivery:<15} proof={proof} "
        f"created={created}"
    )


async def find_signals(
    session: Any,
    *,
    asset: str | None = None,
    status_filter: str | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Query signals that may need reconciliation."""
    from sqlalchemy import select, text

    conditions = []
    if asset:
        conditions.append("lower(s.asset) = lower(:asset)")
    if status_filter:
        conditions.append("lower(s.status) = lower(:status_filter)")

    where = " AND ".join(conditions) if conditions else "1=1"
    params: dict[str, Any] = {"limit": limit}
    if asset:
        params["asset"] = asset
    if status_filter:
        params["status_filter"] = status_filter

    query = text(f"""
        SELECT s.signal_id, s.asset, s.timeframe, s.direction, s.status,
               s.lifecycle_state, s.delivery_state, s.sent_ok,
               s.created_at, s.proof_ok, s.delivery_proof_id,
               s.score, s.entry, s.stop_loss
        FROM signals s
        WHERE {where}
          AND s.status NOT IN ('EXPIRED', 'MISSED_ENTRY', 'SL_HIT', 'TP1_HIT', 'TP2_HIT', 'TP3_HIT', 'BREAKEVEN_STOP')
          AND (s.lifecycle_state IS NULL
               OR s.lifecycle_state IN ('', 'NEW', 'WATCHING_FOR_ENTRY', 'ACTIVE_TRADE', 'STORED', 'CANDIDATE'))
        ORDER BY s.created_at DESC
        LIMIT :limit
    """)

    rows = (await session.execute(query, params)).mappings().all()
    return [dict(row) for row in rows]


async def reconcile(session: Any, record: dict[str, Any], *, dry_run: bool = True) -> dict[str, Any]:
    """Reconcile one signal record, returning the action taken."""
    classification = classify_signal(record)
    new_status, new_lifecycle, reason = reconcile_action(classification)

    if not new_status:
        return {"signal_id": record.get("signal_id"), "classification": classification, "action": "none"}

    signal_id = str(record.get("signal_id") or "")
    result = {
        "signal_id": signal_id,
        "asset": record.get("asset"),
        "classification": classification,
        "action": "reconcile",
        "old_status": str(record.get("status")),
        "old_lifecycle": str(record.get("lifecycle_state")),
        "new_status": new_status,
        "new_lifecycle": new_lifecycle,
        "reason": reason,
    }

    if dry_run:
        result["applied"] = False
        return result

    try:
        from sqlalchemy import text as sa_text

        # Update signal status
        await session.execute(
            sa_text("""
                UPDATE signals
                SET status = :status,
                    lifecycle_state = :lifecycle,
                    updated_at = :now,
                    provenance_note = :reason
                WHERE signal_id = :signal_id
            """),
            {
                "status": new_status,
                "lifecycle": new_lifecycle,
                "now": _utcnow(),
                "reason": reason,
                "signal_id": signal_id,
            },
        )

        # Create audit lifecycle event
        await session.execute(
            sa_text("""
                INSERT INTO signal_tracking_events
                    (signal_id, event_type, event_time, price, meta)
                VALUES
                    (:signal_id, :event_type, :event_time, :price, :meta)
            """),
            {
                "signal_id": signal_id,
                "event_type": "legacy_reconciled",
                "event_time": _utcnow(),
                "price": record.get("entry") or 0,
                "meta": str({
                    "reason": reason,
                    "old_status": str(record.get("status")),
                    "old_lifecycle": str(record.get("lifecycle_state")),
                    "classification": classification,
                    "reconciled_by": "reconcile_signal_lifecycle.py",
                    "dry_run": False,
                }),
            },
        )

        result["applied"] = True
    except Exception as exc:
        result["applied"] = False
        result["error"] = str(exc)

    return result


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile stale signal lifecycle records",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--apply", action="store_true", help="Apply reconciliation (default: dry-run)")
    parser.add_argument("--asset", type=str, default=None, help="Filter by asset symbol")
    parser.add_argument("--status", type=str, default=None, help="Filter by status")
    parser.add_argument("--limit", type=int, default=1000, help="Max records to inspect")
    args = parser.parse_args()

    # Import DB session
    try:
        from db.priority import DBPriority
        from db.session import get_session
    except ImportError as exc:
        logger.error("Cannot import database modules: %s", exc)
        logger.error("Run from project root with PYTHONPATH set correctly")
        return 1

    if not args.apply:
        logger.info("=" * 72)
        logger.info("DRY-RUN MODE — no changes will be applied")
        logger.info("Pass --apply to write changes")
        logger.info("=" * 72)

    stats: dict[str, int] = {}

    async with get_session(priority=DBPriority.BACKGROUND, label="reconcile_signal_lifecycle") as session:
        records = await find_signals(
            session,
            asset=args.asset,
            status_filter=args.status,
            limit=args.limit,
        )
        await session.commit()

    logger.info("Found %d signal(s) to inspect", len(records))

    if not records:
        logger.info("No signals require reconciliation. System state is clean.")
        return 0

    # Classify
    classifications: dict[str, int] = {}
    for record in records:
        cls = classify_signal(record)
        classifications[cls] = classifications.get(cls, 0) + 1

    logger.info("\nClassification breakdown:")
    for cls, count in sorted(classifications.items(), key=lambda x: -x[1]):
        logger.info("  %-30s %d", cls, count)

    # Show actionable records
    actionable = [
        r for r in records
        if classify_signal(r) in ("active_no_proof", "claimed_delivery_no_proof", "watching_no_proof", "stored_no_progress")
    ]

    if not actionable:
        logger.info("\nNo signals require reconciliation. Non-actionable records are benign.")
        fnl = {k: v for k, v in classifications.items() if k not in ("skip_no_id", "already_terminal", "other")}
        logger.info("Remaining: %s", fnl)
        return 0

    logger.info("\n%80s", "=" * 80)
    logger.info("%-14s %-12s %-6s %-7s %-12s %-20s %-15s %s", "Signal ID", "Asset", "TF", "Dir", "Status", "Lifecycle", "Delivery", "Proof")
    logger.info("%-14s %-12s %-6s %-7s %-12s %-20s %-15s %s", "-" * 12, "-" * 10, "-" * 4, "-" * 5, "-" * 10, "-" * 18, "-" * 13, "-" * 5)
    for record in actionable:
        logger.info(display_row(record))
    logger.info("%80s", "=" * 80)

    if args.apply:
        logger.info("\nApplying reconciliation...")
        async with get_session(priority=DBPriority.CRITICAL, label="reconcile_signal_lifecycle_apply") as session:
            results = []
            for record in actionable:
                result = await reconcile(session, record, dry_run=False)
                results.append(result)

            await session.commit()

        applied = sum(1 for r in results if r.get("applied"))
        failed = sum(1 for r in results if r.get("error"))
        logger.info("Reconciliation complete: %d applied, %d failed, %d total", applied, failed, len(results))
        if failed:
            logger.error("Failed records:")
            for r in results:
                if r.get("error"):
                    logger.error("  %s: %s", r.get("signal_id", "?"), r.get("error"))
    else:
        logger.info("\nDRY-RUN: %d signal(s) would be reconciled", len(actionable))
        logger.info("Run with --apply to perform reconciliation")

    return 0


if __name__ == "__main__":
    import asyncio

    sys.exit(asyncio.run(main()))
