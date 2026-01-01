from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

from db.models import Subscription, User


def normalize_tier(tier: str) -> str:
    t = (tier or "").strip().lower()
    if t in {"vip"}:
        return "vip"
    if t in {"premium", "pro"}:
        return "premium"
    return "free"


async def get_or_create_user(
    session: AsyncSession,
    telegram_user_id: int,
    username: Optional[str] = None,
) -> User:
    res = await session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
    user = res.scalar_one_or_none()
    if user is not None:
        if username and user.username != username:
            user.username = username
            await session.flush()
        return user

    user = User(telegram_user_id=telegram_user_id, username=username)
    session.add(user)
    await session.flush()
    return user


async def activate_subscription(
    session: AsyncSession,
    telegram_user_id: int,
    tier: str,
    duration_days: int,
    paystack_reference: Optional[str],
    meta: Dict[str, Any],
) -> Subscription:
    # Idempotency: if reference already exists, return existing subscription.
    if paystack_reference:
        res = await session.execute(
            select(Subscription).where(Subscription.paystack_reference == paystack_reference)
        )
        existing = res.scalar_one_or_none()
        if existing is not None:
            return existing

    user = await get_or_create_user(session, telegram_user_id)

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=max(int(duration_days), 1))

    sub = Subscription(
        user_id=user.id,
        tier=normalize_tier(tier),
        status="active",
        started_at=now,
        expires_at=expires_at,
        paystack_reference=paystack_reference,
        meta=meta or {},
    )
    session.add(sub)
    await session.flush()
    return sub


async def expire_subscriptions(session: AsyncSession) -> int:
    """Mark active subscriptions as expired if past expiry."""
    now = datetime.now(timezone.utc)
    stmt = (
        update(Subscription)
        .where(
            Subscription.status == "active",
            Subscription.expires_at.is_not(None),
            Subscription.expires_at <= now,
        )
        .values(status="expired")
    )
    res = await session.execute(stmt)
    await session.flush()
    # SQLAlchemy typing doesn't guarantee rowcount; treat missing as 0.
    rowcount = getattr(res, "rowcount", None)
    return int(rowcount or 0)
