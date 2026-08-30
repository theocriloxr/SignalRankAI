"""Read-only forensic export of a user's canonical performance ledger."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.session import get_session
from services.performance_ledger import audit_user_performance, get_user_performance_report


def _json(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "__table__"):
        return {column.name: _json(getattr(value, column.name)) for column in value.__table__.columns}
    raise TypeError(type(value).__name__)


async def run(args: argparse.Namespace) -> int:
    async with get_session(priority="background", label="audit_performance_ledger") as session:
        report = await get_user_performance_report(
            session,
            telegram_user_id=args.telegram_user_id,
            days=args.days,
            environment=args.environment,
        )
        audit = await audit_user_performance(
            session,
            telegram_user_id=args.telegram_user_id,
            days=args.days,
        )
        # The service may stage missing ledger rows while reconciling. This tool
        # is deliberately read-only, so never commit them.
        await session.rollback()

    rows = list(report.pop("rows", []))
    payload = {"report": report, "audit": audit, "rows": rows, "mode": "read_only"}
    print(json.dumps(payload, default=_json, indent=2, sort_keys=True))
    if args.csv:
        target = Path(args.csv).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [column.name for column in rows[0].__table__.columns] if rows else [
            "signal_id", "primary_bucket", "final_realized_r", "exclusion_reason"
        ]
        with target.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({name: _json(getattr(row, name, None)) for name in fieldnames})
    return 0 if bool(audit.get("invariant_ok")) else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("telegram_user_id", type=int)
    parser.add_argument("--days", type=int, choices=(7, 30, 90), default=30)
    parser.add_argument("--environment", default=None)
    parser.add_argument("--csv", help="Optional CSV output path")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
