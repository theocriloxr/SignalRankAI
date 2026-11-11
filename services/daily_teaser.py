"""Daily top-3 teaser per asset class (10 Nov 2026; learned from competitor research).

Token Metrics and Danelfin post a daily "top rated" list; it is the free
content that shows what the paid tiers get. Once a day (after
``DAILY_TEASER_HOUR_UTC``, default 12) analytics publishes, per asset class,
the three highest-ranked signals delivered in the last 24 hours: instrument,
side, timeframe and score only. Entry, stop and targets stay with the tiers
that received them, and the list only names signals at least
``DAILY_TEASER_MIN_AGE_MINUTES`` old (default 60), so it never front-runs a
live delivery.

It goes to ``PUBLIC_TELEGRAM_CHANNEL_ID`` when set, as one ``alert``
notification per active free-tier user (web/app notification centre, then
email/push per their preferences), and as a Telegram message to linked
free-tier users (``DAILY_TEASER_TELEGRAM_DM``, default on). The same list is
served at ``GET /public/daily-top`` for the website. A runtime_state marker
per day makes it run once even across restarts. ``DAILY_TEASER_ENABLED=false``
turns it off.
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

_TOP_SQL = """
    SELECT asset_class, asset, direction, timeframe, score, created_at FROM (
        SELECT COALESCE(NULLIF(s.asset_class, ''), 'other') AS asset_class, s.asset, s.direction, s.timeframe,
               s.score, s.created_at,
               ROW_NUMBER() OVER (PARTITION BY COALESCE(NULLIF(s.asset_class, ''), 'other')
                                  ORDER BY s.score DESC, s.created_at DESC) AS rn
        FROM signals s
        WHERE s.created_at >= (NOW() AT TIME ZONE 'utc') - INTERVAL '24 hours'
          AND s.created_at <= (NOW() AT TIME ZONE 'utc') - make_interval(mins => :min_age)
          AND EXISTS (SELECT 1 FROM signal_deliveries d WHERE d.signal_id = s.signal_id AND d.sent_ok)
    ) ranked
    WHERE rn <= 3
    ORDER BY asset_class, score DESC
"""

_CLASS_NAMES = {"fx": "FX", "forex": "FX", "crypto": "Crypto", "stock": "Stocks", "equity": "Stocks",
                "index": "Indices", "indices": "Indices", "commodity": "Commodities", "metal": "Metals"}


def _on(name: str, default: bool = True) -> bool:
    return str(os.getenv(name, "1" if default else "0")).strip().lower() in {"1", "true", "yes", "on"}


def day_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"daily_teaser:{now.date().isoformat()}"


def due(now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return now.hour >= int(os.getenv("DAILY_TEASER_HOUR_UTC", "12") or 12)


async def daily_top(session: Any) -> dict[str, list[dict[str, Any]]]:
    min_age = int(os.getenv("DAILY_TEASER_MIN_AGE_MINUTES", "60") or 60)
    rows = (await session.execute(text(_TOP_SQL), {"min_age": min_age})).mappings().all()
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        side = "BUY" if str(r["direction"] or "").lower() in {"long", "buy"} else "SELL"
        out.setdefault(str(r["asset_class"]), []).append({
            "asset": str(r["asset"]), "side": side, "timeframe": str(r["timeframe"] or ""),
            "score": round(float(r["score"] or 0), 1),
            "created_at": r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else None,
        })
    return out


def teaser_text(top: dict[str, list[dict[str, Any]]]) -> str:
    if not top:
        return ""
    lines = ["🔥 Today's top-ranked setups (last 24h)", ""]
    for asset_class, items in top.items():
        picks = " • ".join(f"{i}) {x['asset']} {x['side']} {x['timeframe']} {x['score']:.0f}"
                           for i, x in enumerate(items, 1))
        lines.append(f"{_CLASS_NAMES.get(asset_class, asset_class.title())}: {picks}")
    lines += ["", "Scores rank setups; they are not a chance of winning. Entry, stop and targets go to "
              "Premium and VIP in real time (/upgrade). Every result, misses included: /track_record."]
    return "\n".join(lines)


async def publish_once(*, now: datetime | None = None, telegram_post=None) -> dict[str, Any]:
    from db.session import get_session

    if not _on("DAILY_TEASER_ENABLED") or not due(now):
        return {"status": "not_due"}
    key = day_key(now)
    async with get_session(priority="analytics", label="daily_teaser", timeout_seconds=20.0) as session:
        claimed = await session.execute(
            text("INSERT INTO runtime_state(key, value, expires_at, updated_at) VALUES (:k, CAST(:v AS JSONB), NULL, NOW()) "
                 "ON CONFLICT (key) DO NOTHING"),
            {"k": key, "v": json.dumps({"claimed_at": datetime.now(timezone.utc).isoformat()})},
        )
        if int(getattr(claimed, "rowcount", 0) or 0) != 1:
            await session.rollback()
            return {"status": "already_published", "day": key}
        top = await daily_top(session)
        body = teaser_text(top)
        if not body:
            await session.commit()
            return {"status": "nothing_to_publish", "day": key}
        users = (await session.execute(text(
            "SELECT id, telegram_user_id FROM users WHERE COALESCE(account_status, 'active') = 'active' "
            "AND lower(COALESCE(tier, 'free')) = 'free'"))).all()
        for user_id, _tg in users:
            await session.execute(
                text("INSERT INTO notification_events(notification_id,user_id,event_type,title,body,severity,"
                     "channel_data,created_at) VALUES (:nid,:uid,'alert','Today''s top setups',:body,'info',"
                     "CAST(:data AS JSONB),NOW()) ON CONFLICT(notification_id) DO NOTHING"),
                {"nid": f"teaser:{key[13:]}:{int(user_id)}"[:36], "uid": int(user_id), "body": body[:4000],
                 "data": json.dumps({"kind": "daily_teaser", "url": "/track-record"})},
            )
        await session.commit()
    from services.weekly_scorecard import _telegram_post

    post = telegram_post or _telegram_post
    targets: list[int | str] = [int(tg) for _uid, tg in users if tg] if _on("DAILY_TEASER_TELEGRAM_DM") else []
    channel = str(os.getenv("PUBLIC_TELEGRAM_CHANNEL_ID") or "").strip()
    if channel:
        targets.append(channel)
    sent = 0
    for chat in targets:
        try:
            sent += 1 if await post(chat, body) else 0
        except Exception:
            continue
        await asyncio.sleep(0.05)
    logger.info("[daily_teaser] day=%s classes=%s users=%s telegram_sent=%s", key, len(top), len(users), sent)
    return {"status": "published", "day": key, "classes": len(top), "users": len(users), "telegram_sent": sent}


async def daily_teaser_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await publish_once()
        except Exception as exc:
            logger.warning("[daily_teaser] publish failed error=%s", type(exc).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=600)
        except asyncio.TimeoutError:
            continue
