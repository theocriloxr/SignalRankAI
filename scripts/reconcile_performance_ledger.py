"""Preview or materialize proof-backed performance ledger rows safely."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.session import get_session
from services.performance_ledger import audit_user_performance, get_user_performance_report


async def run(args: argparse.Namespace) -> int:
    async with get_session(priority="background", label="reconcile_performance_ledger") as session:
        report = await get_user_performance_report(
            session,
            telegram_user_id=args.telegram_user_id,
            days=args.days,
            environment=args.environment,
        )
        audit = await audit_user_performance(
            session, telegram_user_id=args.telegram_user_id, days=args.days
        )
        if args.apply:
            await session.commit()
        else:
            await session.rollback()
    print(json.dumps({
        "mode": "apply" if args.apply else "dry_run",
        "telegram_user_id": args.telegram_user_id,
        "days": args.days,
        "reconciliation_id": report.get("reconciliation_id"),
        "confirmed_deliveries": report.get("delivered"),
        "bucket_sum": sum((report.get("buckets") or {}).values()),
        "invariant_ok": audit.get("invariant_ok"),
        "warning": "Finalized rows are immutable; this command never performs corrections.",
    }, indent=2))
    return 0 if audit.get("invariant_ok") else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("telegram_user_id", type=int)
    parser.add_argument("--days", type=int, choices=(7, 30, 90), default=90)
    parser.add_argument("--environment", default=None)
    parser.add_argument("--apply", action="store_true", help="Commit newly materialized rows")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
