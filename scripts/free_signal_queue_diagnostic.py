"""Inspect stale Free-tier queue rows; mutation requires explicit --apply."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse
import asyncio
from datetime import timedelta

from sqlalchemy import func, select, update

from db.models import FreeSignalQueue
from db.session import get_session
from utils.timeutils import now_utc_naive


async def run(*, stale_hours: int, apply: bool) -> int:
    cutoff = now_utc_naive() - timedelta(hours=max(1, int(stale_hours)))
    async with get_session(priority="background", label="free_queue_diagnostic") as session:
        stale_count = int((await session.execute(
            select(func.count(FreeSignalQueue.id)).where(
                FreeSignalQueue.status == "queued",
                FreeSignalQueue.sent_at.is_(None),
                FreeSignalQueue.deliver_after < cutoff,
            )
        )).scalar() or 0)
        total_queued = int((await session.execute(
            select(func.count(FreeSignalQueue.id)).where(
                FreeSignalQueue.status == "queued",
                FreeSignalQueue.sent_at.is_(None),
            )
        )).scalar() or 0)
        print({
            "mode": "apply" if apply else "dry_run",
            "queued_unsent": total_queued,
            "stale_queued": stale_count,
            "stale_hours": int(stale_hours),
        })
        if not apply or stale_count == 0:
            await session.rollback()
            return stale_count
        result = await session.execute(
            update(FreeSignalQueue)
            .where(
                FreeSignalQueue.status == "queued",
                FreeSignalQueue.sent_at.is_(None),
                FreeSignalQueue.deliver_after < cutoff,
            )
            .values(status="quarantined")
        )
        await session.commit()
        print({"quarantined": int(result.rowcount or 0), "recoverable": True})
        return stale_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stale-hours", type=int, default=24)
    parser.add_argument("--apply", action="store_true", help="quarantine matched rows")
    args = parser.parse_args()
    asyncio.run(run(stale_hours=args.stale_hours, apply=bool(args.apply)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
