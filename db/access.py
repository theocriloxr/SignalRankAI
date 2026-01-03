from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from sqlalchemy import desc, select

from db.models import Subscription, User
from db.session import ENGINE, get_session


def owner_id() -> int:
    try:
        return int(os.getenv("OWNER_TELEGRAM_ID", "0"))
    except ValueError:
        return 0


def is_owner(telegram_user_id: int) -> bool:
    oid = owner_id()
    return bool(oid) and telegram_user_id == oid


async def resolve_user_tier(telegram_user_id: int) -> str:
    """Resolve tier from Postgres if configured.

    Falls back to OWNER or FREE when Postgres is not configured.
    """

    if is_owner(telegram_user_id):
        return "owner"

    if ENGINE is None:
        return "free"

    now = datetime.utcnow()
    async with get_session() as session:
        res_user = await session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
        user = res_user.scalar_one_or_none()
        if user is None:
            return "free"

        res_sub = await session.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user.id,
                Subscription.status == "active",
                (Subscription.expires_at.is_(None)) | (Subscription.expires_at > now),
            )
            .order_by(desc(Subscription.expires_at))
        )
        sub = res_sub.scalars().first()
        if sub is None:
            return "free"
        return sub.tier


async def has_full_access(telegram_user_id: int) -> bool:
    tier = await resolve_user_tier(telegram_user_id)
    return tier in {"premium", "vip", "owner"}
