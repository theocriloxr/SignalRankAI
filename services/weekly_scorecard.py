"""Weekly scorecard to every channel (9 Nov 2026; learned from competitor research).

An honest weekly scorecard of every call, misses included, is the content that
sets SignalRank apart from groups that only post wins. Once per ISO week
(Monday, after ``WEEKLY_SCORECARD_HOUR_UTC``, default 07), analytics:

* adds one ``alert`` notification per active user, which the web/app
  notification centre shows and the email/push dispatcher sends per the user's
  preferences;
* sends it on Telegram to linked active users (``WEEKLY_SCORECARD_TELEGRAM_DM``,
  default on) and to ``PUBLIC_TELEGRAM_CHANNEL_ID`` when set.

A runtime_state marker per ISO week makes it run once even across restarts.
``WEEKLY_SCORECARD_ENABLED=false`` turns it off.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)


def _on(name: str, default: bool = True) -> bool:
    return str(os.getenv(name, "1" if default else "0")).strip().lower() in {"1", "true", "yes", "on"}


def week_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    year, week, _ = now.isocalendar()
    return f"weekly_scorecard:{year}-W{week:02d}"


def due(now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    hour = int(os.getenv("WEEKLY_SCORECARD_HOUR_UTC", "7") or 7)
    return now.weekday() == 0 and now.hour >= hour


async def _claim_week(session: Any, key: str) -> bool:
    result = await session.execute(
        text("INSERT INTO runtime_state(key, value, expires_at, updated_at) VALUES (:k, CAST(:v AS JSONB), NULL, NOW()) "
             "ON CONFLICT (key) DO NOTHING"),
        {"k": key, "v": json.dumps({"claimed_at": datetime.now(timezone.utc).isoformat()})},
    )
    return int(getattr(result, "rowcount", 0) or 0) == 1


async def publish_once(*, now: datetime | None = None, telegram_post=None) -> dict[str, Any]:
    """Publish this week's scorecard if due and not yet published. Returns what happened."""
    from db.session import get_session
    from services.public_track_record import build_track_record, weekly_scorecard_text

    if not _on("WEEKLY_SCORECARD_ENABLED") or not due(now):
        return {"status": "not_due"}
    key = week_key(now)
    async with get_session(label="weekly_scorecard", timeout_seconds=20.0) as session:
        if not await _claim_week(session, key):
            await session.rollback()
            return {"status": "already_published", "week": key}
        record = await build_track_record(session)
        body = weekly_scorecard_text(record)
        users = (await session.execute(text(
            "SELECT id, telegram_user_id FROM users "
            "WHERE COALESCE(account_status, 'active') = 'active'"))).all()
        for user_id, _tg in users:
            await session.execute(
                text("INSERT INTO notification_events(notification_id,user_id,event_type,title,body,severity,"
                     "channel_data,created_at) VALUES (:nid,:uid,'alert','Weekly scorecard',:body,'info',"
                     "CAST(:data AS JSONB),NOW()) ON CONFLICT(notification_id) DO NOTHING"),
                {"nid": f"{key}:{user_id}", "uid": int(user_id), "body": body[:4000],
                 "data": json.dumps({"kind": "weekly_scorecard", "url": "/track-record"})},
            )
        await session.commit()
    sent = 0
    targets: list[int | str] = []
    if _on("WEEKLY_SCORECARD_TELEGRAM_DM"):
        targets.extend(int(tg) for _uid, tg in users if tg)
    channel = str(os.getenv("PUBLIC_TELEGRAM_CHANNEL_ID") or "").strip()
    if channel:
        targets.append(channel)
    post = telegram_post or _telegram_post
    for chat in targets:
        try:
            if await post(chat, body + "\n\nFull record: /track-record on the website."):
                sent += 1
        except Exception:
            continue
        await asyncio.sleep(0.05)  # stay well under Telegram's broadcast limits
    logger.info("[weekly_scorecard] week=%s users=%s telegram_sent=%s", key, len(users), sent)
    return {"status": "published", "week": key, "users": len(users), "telegram_sent": sent}


async def _telegram_post(chat: int | str, message: str) -> bool:
    import httpx

    token = str(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        return False
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                     json={"chat_id": chat, "text": message, "disable_web_page_preview": True})
    return response.status_code == 200


async def weekly_scorecard_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await publish_once()
        except Exception as exc:
            logger.warning("[weekly_scorecard] publish failed error=%s", type(exc).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=900)
        except asyncio.TimeoutError:
            continue
