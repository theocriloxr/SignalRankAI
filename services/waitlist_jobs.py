"""Isolated VIP waitlist scheduler jobs.

These jobs intentionally live outside ``web.app`` so the Railway scheduler does
not need to import the complete HTTP/Telegram surface merely to register two
periodic database tasks.  Importing ``web.app`` can fail when an optional web
integration is unavailable, which previously made both waitlist jobs disappear
without a useful traceback.
"""
from __future__ import annotations

import logging
import os
from datetime import timedelta

from sqlalchemy import select

from db.models import User, VIPWaitlist
from db.priority import DBPriority
from db.repository import count_active_vip_users
from db.session import NoncriticalWriteDropped, get_session
from utils.timeutils import now_utc_naive

logger = logging.getLogger(__name__)


async def _send_telegram_dm(telegram_user_id: int, message: str) -> None:
    token = str(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        logger.warning("[waitlist] Telegram token missing; notification deferred user=%s", telegram_user_id)
        return
    try:
        from telegram import Bot

        async with Bot(token=token) as bot:
            await bot.send_message(chat_id=int(telegram_user_id), text=message)
    except Exception as exc:
        logger.warning(
            "[waitlist] Telegram notification failed user=%s err_type=%s err=%s",
            telegram_user_id,
            type(exc).__name__,
            exc,
            exc_info=True,
        )


async def check_waitlist_capacity_job() -> None:
    """Invite one pending waitlist user when a VIP seat is available."""
    telegram_user_id: int | None = None
    try:
        vip_seat_limit = max(1, int(os.getenv("VIP_SEAT_LIMIT", "20") or 20))
        async with get_session(
            priority=DBPriority.BACKGROUND,
            label="waitlist.capacity",
            timeout_seconds=float(os.getenv("WAITLIST_DB_TIMEOUT_SECONDS", "5") or 5),
        ) as session:
            active_vip = await count_active_vip_users(session)
            if active_vip >= vip_seat_limit:
                await session.rollback()
                logger.info("[waitlist] at capacity: %s/%s", active_vip, vip_seat_limit)
                return

            stmt = (
                select(VIPWaitlist)
                .where(VIPWaitlist.invited_at.is_(None))
                .order_by(VIPWaitlist.joined_at, VIPWaitlist.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            entry = (await session.execute(stmt)).scalars().first()
            if entry is None:
                await session.rollback()
                logger.debug("[waitlist] no pending entries")
                return

            user = (
                await session.execute(select(User).where(User.id == int(entry.user_id)))
            ).scalars().first()
            if user is None:
                await session.rollback()
                logger.warning("[waitlist] user %s not found", entry.user_id)
                return

            now = now_utc_naive()
            entry.invited_at = now
            entry.invite_expires_at = now + timedelta(hours=24)
            telegram_user_id = int(user.telegram_user_id)
            await session.commit()

        await _send_telegram_dm(
            telegram_user_id,
            "You've been invited to SignalRankAI VIP!\nThe invitation expires in 24 hours.",
        )
        logger.info("[waitlist] invited user %s", telegram_user_id)
    except NoncriticalWriteDropped as exc:
        logger.info("[waitlist] capacity check deferred by DB admission: %s", exc)
    except Exception as exc:
        logger.error(
            "[waitlist] capacity check failed err_type=%s err=%s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )


async def monitor_expired_invites_job() -> None:
    """Release expired VIP invitations and notify affected users."""
    recipients: list[int] = []
    try:
        async with get_session(
            priority=DBPriority.BACKGROUND,
            label="waitlist.expiry",
            timeout_seconds=float(os.getenv("WAITLIST_DB_TIMEOUT_SECONDS", "5") or 5),
        ) as session:
            now = now_utc_naive()
            stmt = (
                select(VIPWaitlist, User)
                .join(User, VIPWaitlist.user_id == User.id)
                .where(
                    VIPWaitlist.invite_expires_at.is_not(None),
                    VIPWaitlist.invite_expires_at <= now,
                )
                .with_for_update(skip_locked=True)
            )
            rows = (await session.execute(stmt)).fetchall()
            for entry, user in rows:
                if str(user.tier or "").strip().lower() == "vip":
                    continue
                entry.invited_at = None
                entry.invite_expires_at = None
                recipients.append(int(user.telegram_user_id))
            if rows:
                await session.commit()
            else:
                await session.rollback()

        for telegram_user_id in recipients:
            await _send_telegram_dm(
                telegram_user_id,
                "Your VIP invite expired. Check back later for another opportunity.",
            )
        if recipients:
            logger.info("[waitlist] expired invitations reset count=%s", len(recipients))
    except NoncriticalWriteDropped as exc:
        logger.info("[waitlist] expiry monitor deferred by DB admission: %s", exc)
    except Exception as exc:
        logger.error(
            "[waitlist] expiry monitor failed err_type=%s err=%s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )


# Compatibility names retained for existing imports/tests.
_check_waitlist_capacity_job = check_waitlist_capacity_job
_monitor_expired_invites_job = monitor_expired_invites_job
