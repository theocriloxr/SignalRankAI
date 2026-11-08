"""Email and app (push) notifications for signals and updates, limited per tier (8 Nov 2026).

Owner request: "add email notifications for the signals and notifications so
they can get updates based on their tiers", and "app notifications when they
put it on their desktops or mobile devices".

Every user's signal, lifecycle and paper notifications are already written to
``notification_events`` (the web inbox). This dispatcher sends those same
events by email and/or push to users who switched the channel on
(``notification_preferences.email_enabled`` / ``push_enabled``):

- **email**: a signal is rendered with the same tier formatter as Telegram, so
  each tier sees exactly the detail its plan allows (Free never gets exact
  levels); lifecycle and paper updates use the event's own text. Sent only to
  a verified address, through the existing ``email_outbox`` worker.
- **push**: Expo for the mobile app, Web Push for the installed web app
  (``push_devices``). Short and tier-safe: the event title and body, with a
  link to open it. Skipped inside the user's quiet hours.

``notification_channel_deliveries`` is claimed before sending, so each
(notification, channel) goes out at most once. Read-mostly; no gates, trading
or billing settings are touched.
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

EVENT_TYPES = ("signal", "signal_outcome", "paper_trade", "paper_position", "alert")
EXPO_URL = "https://exp.host/--/api/v2/push/send"


def _app_url(path: str = "") -> str:
    base = str(os.getenv("APP_BASE_URL") or os.getenv("PUBLIC_APP_URL") or "").strip().rstrip("/")
    if base and not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    return f"{base}{path}" if base else path


def telegram_html_to_email(text: str) -> tuple[str, str]:
    """(plain, html) from a Telegram HTML card (b, i, code, a tags and newlines)."""
    body = str(text or "")
    html_body = body.replace("\n", "<br>")
    plain = html.unescape(re.sub(r"<[^>]+>", "", body))
    return plain, html_body


def in_quiet_hours(start: str | None, end: str | None, tz_name: str | None, *, now: datetime | None = None) -> bool:
    if not start or not end:
        return False
    try:
        from zoneinfo import ZoneInfo

        local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(tz_name or "UTC"))
        h1, m1 = (int(x) for x in str(start).split(":")[:2])
        h2, m2 = (int(x) for x in str(end).split(":")[:2])
    except Exception:
        return False
    current, a, b = local.hour * 60 + local.minute, h1 * 60 + m1, h2 * 60 + m2
    if a == b:
        return False
    return a <= current < b if a < b else (current >= a or current < b)


def _signal_payload(row: Any) -> dict[str, Any]:
    keys = ("signal_id", "display_id", "asset", "asset_class", "timeframe", "direction", "entry", "stop_loss",
            "take_profit", "score", "strategy_name", "strategy_group", "regime", "created_at", "expires_at",
            "ml_probability", "ml_probability_calibrated", "rr_estimate", "ml_recovery_mode", "ml_recovery_reason")
    payload = {k: row.get(k) for k in keys if k in row}
    return payload


def render_signal_email(signal: dict[str, Any], tier: str) -> tuple[str, str, str] | None:
    """Subject, plain and HTML for one signal at the user's tier (same formatter as Telegram)."""
    try:
        from signalrank_telegram.formatter import format_signal, format_signal_free_limited
    except Exception:
        return None
    tier_l = str(tier or "free").lower()
    display = "vip" if tier_l in {"professional", "institutional", "admin", "owner"} else tier_l
    text = None
    try:
        text = format_signal(dict(signal), user_tier=tier_l, display_tier=display)
    except Exception:
        text = None
    if not text:
        try:
            text = format_signal_free_limited(dict(signal))
        except Exception:
            text = None
    if not text:
        return None
    asset = str(signal.get("asset") or "Signal")
    direction = str(signal.get("direction") or "").upper()
    subject = f"SignalRankAI: {asset} {direction} {signal.get('timeframe') or ''} signal".strip()
    plain, html_body = telegram_html_to_email(text)
    link = _app_url(f"/app/signals/{signal.get('signal_id')}") if signal.get("signal_id") else _app_url("/app")
    footer_plain = f"\n\nOpen in SignalRankAI: {link}\nYou receive this because email alerts are on in your notification settings."
    footer_html = (f"<p><a href='{html.escape(link)}'>Open in SignalRankAI</a></p>"
                   "<p style='color:#777;font-size:12px'>You receive this because email alerts are on in your "
                   "notification settings. Trading carries risk; signals are not advice.</p>")
    wrapped = (f"<div style='font-family:system-ui,sans-serif;max-width:620px;margin:auto;line-height:1.5'>"
               f"<h2 style='margin:0 0 12px'>SignalRankAI</h2><div>{html_body}</div>{footer_html}</div>")
    return subject[:240], plain + footer_plain, wrapped


def render_event_email(title: str, body: str, link: str) -> tuple[str, str, str]:
    plain = f"{body}\n\nOpen in SignalRankAI: {link}\nYou receive this because email alerts are on in your notification settings."
    wrapped = (f"<div style='font-family:system-ui,sans-serif;max-width:620px;margin:auto;line-height:1.5'>"
               f"<h2 style='margin:0 0 12px'>SignalRankAI</h2><p><b>{html.escape(title)}</b></p>"
               f"<p>{html.escape(body)}</p><p><a href='{html.escape(link)}'>Open in SignalRankAI</a></p>"
               "<p style='color:#777;font-size:12px'>You receive this because email alerts are on in your "
               "notification settings.</p></div>")
    return f"SignalRankAI: {title}"[:240], plain, wrapped


CANDIDATES_SQL = """
SELECT ne.notification_id, ne.user_id, ne.event_type, ne.title, ne.body, ne.channel_data, ne.created_at,
       u.tier, u.primary_email, u.email_verified_at,
       np.email_enabled, np.push_enabled, np.quiet_hours_start, np.quiet_hours_end, np.timezone
FROM notification_events ne
JOIN users u ON u.id = ne.user_id
JOIN notification_preferences np ON np.user_id = ne.user_id
WHERE ne.created_at >= :since AND ne.event_type = ANY(:types)
  AND COALESCE(u.is_blocked, FALSE) IS FALSE
  AND ((np.email_enabled IS TRUE AND NOT EXISTS (SELECT 1 FROM notification_channel_deliveries c
            WHERE c.notification_id = ne.notification_id AND c.channel = 'email'))
    OR (np.push_enabled IS TRUE AND NOT EXISTS (SELECT 1 FROM notification_channel_deliveries c
            WHERE c.notification_id = ne.notification_id AND c.channel = 'push')))
ORDER BY ne.created_at
LIMIT :limit
"""


async def _claim(session, notification_id: str, channel: str, user_id: int) -> bool:
    from sqlalchemy import text

    result = await session.execute(
        text("INSERT INTO notification_channel_deliveries(notification_id, channel, user_id) "
             "VALUES (:n, :c, :u) ON CONFLICT DO NOTHING"),
        {"n": notification_id, "c": channel, "u": int(user_id)},
    )
    return int(getattr(result, "rowcount", 0) or 0) == 1


async def _finish(session, notification_id: str, channel: str, status: str, detail: str = "") -> None:
    from sqlalchemy import text

    await session.execute(
        text("UPDATE notification_channel_deliveries SET status=CAST(:s AS VARCHAR), detail=CAST(:d AS VARCHAR), "
             "sent_at=CASE WHEN CAST(:s AS VARCHAR) IN ('sent','queued') THEN NOW() ELSE sent_at END "
             "WHERE notification_id=:n AND channel=:c"),
        {"s": status, "d": str(detail)[:240], "n": notification_id, "c": channel},
    )


async def _send_email(session, row: dict[str, Any], channel_data: dict[str, Any]) -> tuple[str, str]:
    from sqlalchemy import text

    recipient = str(row.get("primary_email") or "").strip().lower()
    if not recipient or row.get("email_verified_at") is None:
        return "skipped", "no_verified_email"
    signal_id = str(channel_data.get("signal_id") or "")
    rendered = None
    if row["event_type"] == "signal" and signal_id:
        signal_row = (await session.execute(text("SELECT * FROM signals WHERE signal_id=:s"),
                                            {"s": signal_id})).mappings().first()
        if signal_row is not None:
            rendered = render_signal_email(_signal_payload(dict(signal_row)), str(row.get("tier") or "free"))
    if rendered is None:
        link = _app_url(f"/app/signals/{signal_id}") if signal_id else _app_url("/app/notifications")
        rendered = render_event_email(str(row.get("title") or "Update"), str(row.get("body") or ""), link)
    subject, plain, html_body = rendered
    from uuid import uuid4

    await session.execute(
        text("INSERT INTO email_outbox(email_id,user_id,recipient,template,subject,plain_body,html_body,context,"
             "idempotency_key,status,next_attempt_at) VALUES(:id,:uid,:to,:tpl,:subj,:plain,:html,"
             "CAST(:ctx AS JSONB),:key,'pending',NOW()) "
             "ON CONFLICT(idempotency_key) WHERE idempotency_key IS NOT NULL DO NOTHING"),
        {"id": str(uuid4()), "uid": int(row["user_id"]), "to": recipient,
         "tpl": f"notify_{row['event_type']}"[:64], "subj": subject, "plain": plain, "html": html_body,
         "ctx": json.dumps({"notification_id": row["notification_id"]}),
         "key": f"notify:{row['notification_id']}:email"},
    )
    return "queued", "email_outbox"


async def _send_push(session, row: dict[str, Any], channel_data: dict[str, Any], *, client=None) -> tuple[str, str]:
    from sqlalchemy import text

    from services.security import decrypt_secret

    if in_quiet_hours(row.get("quiet_hours_start"), row.get("quiet_hours_end"), row.get("timezone")):
        return "skipped", "quiet_hours"
    devices = (await session.execute(
        text("SELECT push_device_id, provider, encrypted_push_token FROM push_devices "
             "WHERE user_id=:u AND active IS TRUE AND revoked_at IS NULL"), {"u": int(row["user_id"])}
    )).all()
    if not devices:
        return "skipped", "no_devices"
    signal_id = str(channel_data.get("signal_id") or "")
    link = f"/app/signals/{signal_id}" if signal_id else "/app/notifications"
    title, body = str(row.get("title") or "SignalRankAI")[:120], str(row.get("body") or "")[:240]
    sent, gone = 0, []
    expo_messages, expo_ids = [], []
    vapid_key = None
    for device_id, provider, encrypted in devices:
        token = decrypt_secret(str(encrypted or "")) or ""
        if not token:
            continue
        if provider == "expo":
            expo_messages.append({"to": token, "title": title, "body": body, "sound": "default",
                                  "channelId": "signals", "data": {"url": link, "notification_id": row["notification_id"]}})
            expo_ids.append(device_id)
        elif provider == "webpush":
            from services.web_push import send_web_push, vapid_private_key

            try:
                subscription = json.loads(token)
            except ValueError:
                gone.append(device_id)
                continue
            vapid_key = vapid_key or await vapid_private_key(session)
            ok, reason = await send_web_push(subscription, {"title": title, "body": body, "url": link,
                                                            "tag": row["notification_id"]}, vapid_key, client=client)
            if ok:
                sent += 1
            elif reason == "gone":
                gone.append(device_id)
    if expo_messages:
        import httpx

        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if os.getenv("EXPO_ACCESS_TOKEN"):
            headers["Authorization"] = f"Bearer {os.getenv('EXPO_ACCESS_TOKEN')}"
        owns = client is None
        http = client or httpx.AsyncClient(timeout=10.0)
        try:
            response = await http.post(EXPO_URL, json=expo_messages, headers=headers)
            tickets = (response.json() or {}).get("data") or [] if response.status_code == 200 else []
        except Exception:
            tickets = []
        finally:
            if owns:
                await http.aclose()
        for device_id, ticket in zip(expo_ids, tickets):
            if (ticket or {}).get("status") == "ok":
                sent += 1
            elif ((ticket or {}).get("details") or {}).get("error") == "DeviceNotRegistered":
                gone.append(device_id)
    if gone:
        await session.execute(text("UPDATE push_devices SET active=FALSE, revoked_at=NOW() "
                                   "WHERE push_device_id = ANY(:ids)"), {"ids": gone})
    return ("sent", f"devices={sent}") if sent else ("failed", f"devices=0 gone={len(gone)}")


async def dispatch_once(*, limit: int = 100, lookback_hours: float = 2.0, client=None) -> dict[str, int]:
    from datetime import timedelta

    from sqlalchemy import text

    from db.session import get_session

    counters = {"events": 0, "email_queued": 0, "push_sent": 0, "skipped": 0, "failed": 0}
    since = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).replace(tzinfo=None)
    async with get_session(label="notification_channels.dispatch", timeout_seconds=30) as session:
        rows = (await session.execute(text(CANDIDATES_SQL),
                                      {"since": since, "types": list(EVENT_TYPES), "limit": int(limit)})).mappings().all()
        for raw in rows:
            row = dict(raw)
            counters["events"] += 1
            channel_data = row.get("channel_data") or {}
            if isinstance(channel_data, str):
                try:
                    channel_data = json.loads(channel_data)
                except ValueError:
                    channel_data = {}
            for channel, enabled in (("email", row.get("email_enabled")), ("push", row.get("push_enabled"))):
                if not enabled or not await _claim(session, row["notification_id"], channel, row["user_id"]):
                    continue
                try:
                    if channel == "email":
                        status, detail = await _send_email(session, row, channel_data)
                    else:
                        status, detail = await _send_push(session, row, channel_data, client=client)
                except Exception as exc:
                    status, detail = "failed", type(exc).__name__
                await _finish(session, row["notification_id"], channel, status, detail)
                key = {"queued": "email_queued", "sent": "push_sent"}.get(status, status if status in counters else "failed")
                counters[key] += 1
            await session.commit()
    return counters
