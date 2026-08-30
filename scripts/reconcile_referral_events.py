"""Reconcile referral deep-link starts captured in bot_events.

Dry-run by default. Use --apply after deploying migration 0032. This repairs
referrals that were lost when the old /start handler swallowed referral errors.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import timedelta

from sqlalchemy import select

from db.models import BotEvent, User
from db.pg_features import process_referral_start
from db.session import get_session
from utils.timeutils import now_utc_naive


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Persist repaired attributions/rewards")
    parser.add_argument("--days", type=int, default=30, help="Lookback window")
    parser.add_argument("--limit", type=int, default=5000, help="Maximum start events to inspect")
    return parser.parse_args()


async def _load_candidates(days: int, limit: int) -> list[dict]:
    cutoff = now_utc_naive() - timedelta(days=max(1, int(days)))
    async with get_session(
        priority="analytics",
        label="referral.reconcile.scan",
        timeout_seconds=20.0,
    ) as session:
        rows = list((await session.execute(
            select(BotEvent, User.telegram_user_id)
            .join(User, User.id == BotEvent.user_id)
            .where(BotEvent.event_type == "user_start", BotEvent.created_at >= cutoff)
            .order_by(BotEvent.id.asc())
            .limit(max(1, int(limit)))
        )).all())
    candidates: list[dict] = []
    for event, telegram_user_id in rows:
        meta = dict(event.meta or {})
        ref_token = str(meta.get("ref_token") or "").strip()
        if not ref_token:
            continue
        code = ref_token[4:] if ref_token.startswith("ref_") else ref_token
        referral_meta = meta.get("referral") if isinstance(meta.get("referral"), dict) else {}
        prior_status = str((referral_meta or {}).get("status") or "missing")
        if prior_status in {"attributed", "reward_granted", "reward_already_granted", "already_referred"}:
            continue
        candidates.append({
            "event_id": int(event.id),
            "telegram_user_id": int(telegram_user_id),
            "code": code,
            "is_new": bool(meta.get("is_new")),
            "prior_status": prior_status,
        })
    return candidates


async def _apply_candidate(candidate: dict, apply: bool) -> dict:
    if not apply:
        return {"status": "dry_run", **candidate}
    async with get_session(
        priority="critical",
        label="referral.reconcile.apply",
        timeout_seconds=20.0,
    ) as session:
        result = await process_referral_start(
            session,
            referred_telegram_user_id=int(candidate["telegram_user_id"]),
            referral_code=str(candidate["code"]),
            is_new_user=bool(candidate["is_new"]),
        )
        await session.commit()
        return {**candidate, **result}


async def main() -> int:
    args = _parse_args()
    candidates = await _load_candidates(args.days, args.limit)
    counts: Counter[str] = Counter()
    print(f"Referral events eligible for reconciliation: {len(candidates)}")
    for candidate in candidates:
        try:
            result = await _apply_candidate(candidate, bool(args.apply))
            status = str(result.get("status") or "unknown")
            counts[status] += 1
            print(
                f"event={candidate['event_id']} user={candidate['telegram_user_id']} "
                f"prior={candidate['prior_status']} result={status}"
            )
        except Exception as exc:
            counts[f"error:{type(exc).__name__}"] += 1
            print(
                f"event={candidate['event_id']} user={candidate['telegram_user_id']} "
                f"error={type(exc).__name__}: {exc}"
            )
    print("Summary:", dict(sorted(counts.items())))
    if not args.apply:
        print("Dry run only. Re-run with --apply to persist valid repairs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
