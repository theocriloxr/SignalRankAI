"""List pending cross-channel account merge reviews without mutating user data.

Ambiguous Telegram/app duplicates are deliberately not auto-merged. This tool
provides owner/support evidence for a controlled review workflow.
"""
from __future__ import annotations

import argparse
import asyncio
import json

from sqlalchemy import text

from db.session import DBPriority, get_session


async def _run(limit: int) -> list[dict]:
    async with get_session(
        priority=DBPriority.INTERACTIVE,
        label="identity.merge_review.list",
        timeout_seconds=15,
    ) as session:
        rows = (
            await session.execute(
                text(
                    "SELECT merge_id,canonical_user_id,merged_user_id,status,evidence,created_by,created_at "
                    "FROM account_merge_records WHERE status='pending_review' "
                    "ORDER BY created_at ASC LIMIT :limit"
                ),
                {"limit": max(1, min(int(limit), 500))},
            )
        ).mappings().all()
        return [dict(row) for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_run(args.limit)), indent=2, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
