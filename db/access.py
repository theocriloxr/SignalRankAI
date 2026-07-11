from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from sqlalchemy import desc, select

from db.models import Subscription, User
from db.session import get_session, is_db_configured


def owner_id() -> int:
    from config import config
    return int(getattr(config, "OWNER_TELEGRAM_ID", 0) or 0)


def is_owner(telegram_user_id: int) -> bool:
    oid = owner_id()
    return bool(oid) and telegram_user_id == oid


async def _try_sync_owner_tier(telegram_user_id: int) -> None:
    """Best-effort owner tier synchronization in DB."""
    try:
        async with get_session() as session:
            res_user = await session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
            user = res_user.scalar_one_or_none()
            if user is not None and str(getattr(user, "tier", "") or "").strip().lower() != "owner":
                user.tier = "owner"
                await session.commit()
    except Exception:
        pass


async def resolve_user_tier(telegram_user_id: int) -> str:
    """Resolve tier from Postgres if configured.

    Falls back to OWNER or FREE when Postgres is not configured.
    """

    if is_owner(telegram_user_id):
        # Ensure DB reflects owner tier when possible.
        await _try_sync_owner_tier(telegram_user_id)
        return "owner"

    if not is_db_configured():
        return "free"

    now = datetime.utcnow()
    async with get_session() as session:
        res_user = await session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
        user = res_user.scalar_one_or_none()
        if user is None:
            return "free"

        # If user tier was manually elevated (admin/owner), respect it.
        try:
            t = str(getattr(user, "tier", "") or "").strip().lower()
            if t in {"admin", "owner"}:
                return t
        except Exception:
            pass

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
            # Downgrade cached subscriber tiers when no active subscription.
            try:
                if str(getattr(user, "tier", "") or "").strip().lower() in {"premium", "vip"}:
                    user.tier = "free"
                    await session.commit()
            except Exception:
                pass
            return str(getattr(user, "tier", "free") or "free")

        # Sync cached tier from subscription.
        try:
            sub_tier = str(sub.tier or "free").strip().lower()
            if str(getattr(user, "tier", "") or "").strip().lower() != sub_tier:
                user.tier = sub_tier
                await session.commit()
        except Exception:
            pass
        return str(sub.tier or "free")


async def has_full_access(telegram_user_id: int) -> bool:
    tier = await resolve_user_tier(telegram_user_id)
    return tier in {"premium", "vip", "owner"}
