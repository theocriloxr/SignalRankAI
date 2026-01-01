from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from db.models import Subscription, User


def _env_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or str(default)).strip())
    except Exception:
        return default


async def get_active_subscription(
    session: AsyncSession,
    telegram_user_id: int,
    tier: str,
) -> Optional[Subscription]:
    tier_norm = normalize_tier(tier)
    now = datetime.now(timezone.utc)
    res = await session.execute(
        select(Subscription)
        .join(User, User.id == Subscription.user_id)
        .where(
            User.telegram_user_id == telegram_user_id,
            Subscription.status == "active",
            Subscription.tier == tier_norm,
            Subscription.expires_at.is_not(None),
            Subscription.expires_at > now,
        )
        .order_by(Subscription.expires_at.desc())
    )
    return res.scalars().first()


async def count_active_vip_users(
    session: AsyncSession,
    exclude_telegram_user_ids: set[int],
) -> int:
    now = datetime.now(timezone.utc)
    q = (
        select(func.count(func.distinct(Subscription.user_id)))
        .select_from(Subscription)
        .join(User, User.id == Subscription.user_id)
        .where(
            Subscription.status == "active",
            Subscription.tier == "vip",
            Subscription.expires_at.is_not(None),
            Subscription.expires_at > now,
        )
    )

    if exclude_telegram_user_ids:
        q = q.where(User.telegram_user_id.not_in(exclude_telegram_user_ids))

    res = await session.execute(q)
    return int(res.scalar() or 0)


def normalize_tier(tier: str) -> str:
    t = (tier or "").strip().lower()
    if t in {"vip", "owner", "admin"}:
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
    try:
        await session.flush()
        return user
    except IntegrityError:
        # Another concurrent request likely created the same telegram_user_id.
        # Roll back the failed INSERT and re-select.
        await session.rollback()
        res2 = await session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
        existing2 = res2.scalar_one_or_none()
        if existing2 is None:
            raise
        if username and existing2.username != username:
            existing2.username = username
            await session.flush()
        return existing2


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
    tier_norm = normalize_tier(tier)
    add_days = max(int(duration_days), 1)

    # Renewal behavior: if user already has an active subscription for the same tier, extend it.
    existing = await get_active_subscription(session, telegram_user_id=telegram_user_id, tier=tier_norm)
    if existing is not None and existing.expires_at is not None:
        existing.expires_at = existing.expires_at + timedelta(days=add_days)
        existing.meta = {**(existing.meta or {}), **(meta or {})}
        if paystack_reference and not existing.paystack_reference:
            existing.paystack_reference = paystack_reference
        await session.flush()
        return existing

    expires_at = now + timedelta(days=add_days)

    sub = Subscription(
        user_id=user.id,
        tier=tier_norm,
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
