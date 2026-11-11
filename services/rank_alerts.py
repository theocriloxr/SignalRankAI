"""Rank-change alerts (10 Nov 2026; learned from competitor research).

Danelfin and Token Metrics alert when an asset's rating changes. For
SignalRank, a rank change that matters to a trader is a newer signal on an
instrument they still hold an open earlier signal on:

* flip: the new signal is the other direction;
* upgrade / downgrade: same direction, score moved by at least
  ``RANK_ALERT_SCORE_DELTA`` points (default 10).

"Still open" means the earlier signal's lifecycle is not terminal (TP3, stop,
breakeven, missed entry, expired, time stop). Recipients are the users the
earlier signal was delivered to (Telegram or web). Each alert is one
``alert`` notification per user, so the web/app notification centre shows it
and the email/push dispatcher sends it per the user's preferences, plus a
Telegram message to linked users (``RANK_ALERT_TELEGRAM_DM``, default on).
The notification id is derived from (earlier signal, newer signal, user), so
an alert is sent once even across restarts. No new levels are included: the
newer signal reaches each user only through their own tier's delivery.

``RANK_ALERTS_ENABLED=false`` turns it off.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import text

logger = logging.getLogger(__name__)

_TERMINAL = ("TP3_HIT", "SL_HIT", "BREAKEVEN_STOP", "MISSED_ENTRY", "EXPIRED", "CLOSED_TIME_STOP")

_PAIRS_SQL = f"""
    SELECT n.signal_id AS new_id, n.asset, n.direction AS new_direction, n.score AS new_score,
           n.timeframe AS new_timeframe,
           o.signal_id AS old_id, o.direction AS old_direction, o.score AS old_score, o.timeframe AS old_timeframe
    FROM signals n
    JOIN signals o ON o.asset = n.asset AND o.signal_id <> n.signal_id
         AND o.created_at < n.created_at
         AND o.created_at >= n.created_at - make_interval(hours => :lookback)
    LEFT JOIN signal_lifecycles l ON l.signal_id = o.signal_id
    WHERE n.created_at >= (NOW() AT TIME ZONE 'utc') - make_interval(mins => :window)
      AND COALESCE(l.state, '') NOT IN {_TERMINAL}
    ORDER BY n.created_at DESC
    LIMIT 200
"""

_RECIPIENTS_SQL = """
    SELECT u.id, u.telegram_user_id
    FROM users u
    WHERE COALESCE(u.account_status, 'active') = 'active'
      AND (EXISTS (SELECT 1 FROM signal_deliveries d WHERE d.user_id = u.id AND d.signal_id = :sid AND d.sent_ok)
           OR EXISTS (SELECT 1 FROM notification_events ne WHERE ne.user_id = u.id AND ne.event_type = 'signal'
                      AND ne.channel_data->>'signal_id' = :sid))
"""


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


def _side(direction: Any) -> str:
    return "long" if str(direction or "").strip().lower() in {"long", "buy", "bullish"} else "short"


def classify(old_direction: Any, old_score: Any, new_direction: Any, new_score: Any,
             *, delta: float | None = None) -> str | None:
    """'flip', 'upgrade', 'downgrade' or None (no alert)."""
    if _side(old_direction) != _side(new_direction):
        return "flip"
    try:
        change = float(new_score) - float(old_score)
    except (TypeError, ValueError):
        return None
    threshold = _env_float("RANK_ALERT_SCORE_DELTA", 10.0) if delta is None else delta
    if change >= threshold:
        return "upgrade"
    if change <= -threshold:
        return "downgrade"
    return None


def alert_text(kind: str, pair: dict[str, Any]) -> tuple[str, str]:
    asset = str(pair.get("asset") or "")
    old_side = "BUY" if _side(pair.get("old_direction")) == "long" else "SELL"
    new_side = "BUY" if _side(pair.get("new_direction")) == "long" else "SELL"
    old_score, new_score = float(pair.get("old_score") or 0), float(pair.get("new_score") or 0)
    ref = str(pair.get("old_id") or "")[:8]
    if kind == "flip":
        title = f"Rank flip on {asset}"
        body = (f"🔄 Rank flip on {asset}: your open {old_side} ({old_score:.0f}/100, ref {ref}) now faces a newer "
                f"{new_side} setup ranked {new_score:.0f}/100. The engine's read has turned; check your position "
                "against its stop and invalidation.")
    else:
        arrow = "⬆️" if kind == "upgrade" else "⬇️"
        word = "upgraded" if kind == "upgrade" else "downgraded"
        title = f"{asset} rank {word}"
        body = (f"{arrow} {asset} {old_side} rank {word}: a newer {new_side} setup is ranked {new_score:.0f}/100, "
                f"against {old_score:.0f}/100 for your open signal (ref {ref}).")
    return title, body + " Not advice to act; your earlier signal's plan still applies until it closes."


async def run_once(*, telegram_post=None) -> dict[str, Any]:
    from db.session import get_session

    lookback = int(_env_float("RANK_ALERT_LOOKBACK_HOURS", 48))
    window = int(_env_float("RANK_ALERT_WINDOW_MINUTES", 30))
    sent: list[tuple[int | None, str]] = []
    created = 0
    async with get_session(priority="analytics", label="rank_alerts", timeout_seconds=20.0) as session:
        pairs = [dict(r) for r in (await session.execute(
            text(_PAIRS_SQL), {"lookback": lookback, "window": window})).mappings().all()]
        for pair in pairs:
            kind = classify(pair["old_direction"], pair["old_score"], pair["new_direction"], pair["new_score"])
            if not kind:
                continue
            title, body = alert_text(kind, pair)
            users = (await session.execute(text(_RECIPIENTS_SQL), {"sid": pair["old_id"]})).all()
            for user_id, telegram_id in users:
                nid = str(uuid5(NAMESPACE_URL, f"signalrank:rank-alert:{pair['old_id']}:{pair['new_id']}:{int(user_id)}"))
                result = await session.execute(
                    text("INSERT INTO notification_events(notification_id,user_id,event_type,title,body,severity,"
                         "channel_data,created_at) VALUES (:nid,:uid,'alert',:title,:body,'warning',"
                         "CAST(:data AS JSONB),NOW()) ON CONFLICT(notification_id) DO NOTHING"),
                    {"nid": nid, "uid": int(user_id), "title": title[:200], "body": body,
                     "data": json.dumps({"kind": f"rank_{kind}", "signal_id": pair["old_id"],
                                         "newer_signal_id": pair["new_id"], "url": f"/app/signals/{pair['old_id']}"})},
                )
                if int(getattr(result, "rowcount", 0) or 0) == 1:
                    created += 1
                    sent.append((int(telegram_id) if telegram_id else None, body))
        await session.commit()
    telegram_sent = 0
    if str(os.getenv("RANK_ALERT_TELEGRAM_DM", "1")).strip().lower() in {"1", "true", "yes", "on"}:
        from services.weekly_scorecard import _telegram_post

        post = telegram_post or _telegram_post
        for chat, body in sent:
            if not chat:
                continue
            try:
                telegram_sent += 1 if await post(chat, body) else 0
            except Exception:
                continue
            await asyncio.sleep(0.05)
    if created:
        logger.info("[rank_alerts] alerts=%s telegram_sent=%s", created, telegram_sent)
    return {"alerts": created, "telegram_sent": telegram_sent}


async def rank_alerts_loop(stop: asyncio.Event) -> None:
    interval = max(30.0, _env_float("RANK_ALERT_INTERVAL_SECONDS", 120.0))
    while not stop.is_set():
        try:
            await run_once()
        except Exception as exc:
            logger.warning("[rank_alerts] run failed error=%s", type(exc).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue
