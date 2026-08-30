#!/usr/bin/env python3
"""Inspect or quarantine queued FREE-tier deliveries.

Dry-run is the default. Use only in staging/owner recovery after accidental free
signal distribution. The command never deletes rows; it moves selected queued
rows to a non-deliverable status with an auditable timestamp.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update

from db.models import FreeSignalQueue
from db.session import get_session


async def run(*, apply: bool, max_age_minutes: int, status: str) -> dict:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=max_age_minutes)
    async with get_session(
        priority="interactive",
        label="ops.quarantine_free_signal_queue",
        timeout_seconds=15,
    ) as session:
        count = int(
            (
                await session.execute(
                    select(func.count(FreeSignalQueue.id)).where(
                        FreeSignalQueue.status == "queued",
                        FreeSignalQueue.queued_at <= cutoff,
                    )
                )
            ).scalar_one()
            or 0
        )
        sample_rows = (
            await session.execute(
                select(
                    FreeSignalQueue.id,
                    FreeSignalQueue.user_id,
                    FreeSignalQueue.signal_id,
                    FreeSignalQueue.asset,
                    FreeSignalQueue.timeframe,
                    FreeSignalQueue.queued_at,
                    FreeSignalQueue.deliver_after,
                )
                .where(
                    FreeSignalQueue.status == "queued",
                    FreeSignalQueue.queued_at <= cutoff,
                )
                .order_by(FreeSignalQueue.queued_at.asc())
                .limit(100)
            )
        ).mappings().all()
        changed = 0
        if apply and count:
            result = await session.execute(
                update(FreeSignalQueue)
                .where(
                    FreeSignalQueue.status == "queued",
                    FreeSignalQueue.queued_at <= cutoff,
                )
                .values(status=status)
            )
            changed = int(getattr(result, "rowcount", 0) or 0)
            await session.commit()
        else:
            await session.rollback()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "apply": apply,
        "cutoff": cutoff.isoformat(),
        "target_status": status,
        "matching_queued_rows": count,
        "changed_rows": changed,
        "sample": [dict(row) for row in sample_rows],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--max-age-minutes", type=int, default=0)
    parser.add_argument("--status", choices=("suppressed", "expired", "cancelled"), default="suppressed")
    args = parser.parse_args()
    payload = asyncio.run(
        run(
            apply=args.apply,
            max_age_minutes=max(0, args.max_age_minutes),
            status=args.status,
        )
    )
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
