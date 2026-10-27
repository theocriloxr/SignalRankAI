"""Preview or complete one reviewed Telegram/web account merge.

Preview (default) is read-only. ``--apply`` moves the archived account's history
onto the kept account in a single transaction and requires the merge id to be
repeated. Rows that cannot move are kept and counted; nothing is deleted.

    python -m tools.complete_account_merge MERGE_ID
    python -m tools.complete_account_merge MERGE_ID --apply --confirm-merge-id MERGE_ID --reviewer-user-id 1
"""

from __future__ import annotations

import argparse
import asyncio
import json

from db.session import DBPriority, get_session
from services.platform.account_merge import apply_account_merge, plan_account_merge


async def _run(merge_id: str, apply: bool, reviewer_user_id: int | None) -> dict:
    async with get_session(
        priority=DBPriority.INTERACTIVE,
        label="identity.merge_review.complete" if apply else "identity.merge_review.preview",
        timeout_seconds=60,
    ) as session:
        if not apply:
            plan = await plan_account_merge(session, merge_id)
            await session.rollback()
            return {"mode": "preview", "plan": plan}
        evidence = await apply_account_merge(session, merge_id, reviewer_user_id=int(reviewer_user_id))
        await session.commit()
        return {"mode": "applied", "merge": evidence}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("merge_id")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-merge-id")
    parser.add_argument("--reviewer-user-id", type=int)
    args = parser.parse_args()
    if args.apply and (args.confirm_merge_id != args.merge_id or not args.reviewer_user_id):
        parser.error("--apply requires --confirm-merge-id equal to the merge id and --reviewer-user-id")
    print(json.dumps(asyncio.run(_run(args.merge_id, args.apply, args.reviewer_user_id)),
                     indent=2, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
