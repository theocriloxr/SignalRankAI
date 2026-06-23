from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from sqlalchemy import desc, select

from db.models import Subscription, User
from db.session import get_session, is_db_configured

logger = logging.getLogger(__name__)


def owner_id() -> int:
    from config import config

    return int(getattr(config, "OWNER_TELEGRAM_ID", 0) or 0)


def is_owner(telegram_user_id: int) -> bool:
    oid = owner_id()
    return bool(oid) and telegram_user_id == oid


async def _try_sync_owner_tier(telegram_user_id: int) -> None:
    """Best-effort owner tier synchronization in DB."""
    try:
        async with get_session() as typed_session:
            user_stmt = select(User).where(User.telegram_user_id == telegram_user_id)
            res_user = await typed_session.execute(user_stmt)
            user = res_user.scalar_one_or_none()

            if user is not None and str(user.tier or "").strip().lower() != "owner":
                user.tier = "owner"
                await typed_session.commit()
    except Exception:
        logger.debug("owner tier sync failed: %s", traceback.format_exc())


async def resolve_user_tier(telegram_user_id: int) -> str:
    """Resolve tier from Postgres if configured.

    Falls back to OWNER or FREE when Postgres is not configured.
    """
    if is_owner(telegram_user_id):
        await _try_sync_owner_tier(telegram_user_id)
        return "owner"

    if not is_db_configured():
        return "free"

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    async with get_session() as typed_session:
        user_stmt = select(User).where(User.telegram_user_id == telegram_user_id)
        res_user = await typed_session.execute(user_stmt)
        user = res_user.scalar_one_or_none()

        if user is None:
            return "free"

        # If user tier was manually elevated (admin/owner), respect it.
        try:
            user_tier = str(user.tier or "").strip().lower()
            if user_tier in {"admin", "owner"}:
                return user_tier
        except Exception:
            logger.debug("failed to parse user tier for user_id=%s: %s", telegram_user_id, traceback.format_exc())

        sub_stmt = (
            select(Subscription)
            .where(
                Subscription.user_id == user.id,
                Subscription.status == "active",
                (Subscription.expires_at.is_(None)) | (Subscription.expires_at > now),
            )
            .order_by(desc(Subscription.expires_at))
        )
        res_sub = await typed_session.execute(sub_stmt)
        sub = res_sub.scalars().first()

        if sub is None:
            # Downgrade cached subscriber tiers when no active subscription.
            try:
                if str(user.tier or "").strip().lower() in {"premium", "vip"}:
                    user.tier = "free"
                    await typed_session.commit()
            except Exception:
                logger.debug(
                    "tier downgrade commit failed for user_id=%s: %s",
                    telegram_user_id,
                    traceback.format_exc(),
                )
            return str(user.tier or "free")

        # Sync cached tier from subscription.
        try:
            sub_tier = str(sub.tier or "free").strip().lower()
            if str(user.tier or "").strip().lower() != sub_tier:
                user.tier = sub_tier
                await typed_session.commit()
        except Exception:
            logger.debug(
                "tier sync commit failed for user_id=%s: %s",
                telegram_user_id,
                traceback.format_exc(),
            )

        return str(sub.tier or "free")


async def has_full_access(telegram_user_id: int) -> bool:
    tier = await resolve_user_tier(telegram_user_id)
    return tier in {"premium", "vip", "owner"}
