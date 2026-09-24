#!/usr/bin/env python3
"""Normalize legacy Signal rows whose expired flag conflicts with an open-like status.

Dry-run by default. --apply updates only expired=true rows in active/open/issued
states. Terminal outcome/closed/superseded states are intentionally untouched.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select, update

from db.models import Signal
from db.session import get_session


_OPEN_LIKE = ("active", "open", "issued")


async def _run(*, apply: bool) -> dict[str, int]:
    async with get_session(
        priority="background",
        label="expired_signal_status_backfill",
        timeout_seconds=30.0,
        drop_if_busy=False,
    ) as session:
        predicate = (
            Signal.expired.is_(True)
            & func.lower(func.coalesce(Signal.status, "")).in_(_OPEN_LIKE)
        )
        count = int((await session.execute(
            select(func.count(Signal.signal_id)).where(predicate)
        )).scalar() or 0)
        updated = 0
        if apply and count:
            result = await session.execute(
                update(Signal)
                .where(predicate)
                .values(status="expired")
            )
            updated = int(result.rowcount or 0)
            await session.commit()
        else:
            await session.rollback()
        return {"matched": count, "updated": updated}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(_run(apply=bool(args.apply)))
    print("[expired_signal_status_backfill] " + json.dumps(
        {"apply": bool(args.apply), **result},
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
