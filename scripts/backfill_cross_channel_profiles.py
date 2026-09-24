#!/usr/bin/env python3
"""Safely materialize linked Telegram trading profiles into canonical web keys.

Dry-run is the default. Pass --apply to write only missing canonical records.
Existing canonical records are never overwritten.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.session import get_session
from services.user_intelligence import backfill_linked_platform_trading_preferences


async def _run(*, apply: bool, limit: int) -> dict[str, int]:
    async with get_session(
        priority="background",
        label="cross_channel_profile_backfill",
        timeout_seconds=30.0,
    ) as session:
        result = await backfill_linked_platform_trading_preferences(
            session,
            limit=limit,
            apply=apply,
        )
        if apply:
            await session.commit()
        else:
            await session.rollback()
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write missing canonical profiles")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    result = asyncio.run(_run(apply=bool(args.apply), limit=int(args.limit)))
    print("[profile_backfill] " + json.dumps({"apply": bool(args.apply), **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
