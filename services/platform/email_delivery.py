"""Transactional account-email outbox with optional SMTP delivery.

Account flows write to PostgreSQL first.  A worker may call
``deliver_email_outbox_batch``; missing SMTP credentials leave messages queued
instead of losing them or blocking registration/login requests.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy import text

from db.session import get_session, is_db_configured

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class QueuedEmail:
    email_id: str
    recipient: str
    template: str


def _sender() -> str:
    return str(os.getenv("EMAIL_FROM") or "SignalRankAI <no-reply@signalrank.ai>").strip()


def _smtp_configured() -> bool:
    return bool(str(os.getenv("SMTP_HOST") or "").strip())


def render_account_email(template: str, context: Mapping[str, Any]) -> tuple[str, str, str]:
    """Return subject, plain body and simple HTML for supported templates."""
    app_name = str(os.getenv("APP_NAME") or "SignalRankAI")
    link = str(context.get("link") or "")
    expires_minutes = int(context.get("expires_minutes") or 15)
    templates: dict[str, tuple[str, str]] = {
        "verify_email": (
            f"Verify your {app_name} email",
            f"Verify your email by opening this single-use link within {expires_minutes} minutes:\n\n{link}\n\nIf you did not request this, ignore this message.",
        ),
        "magic_login": (
            f"Your {app_name} sign-in link",
            f"Open this single-use sign-in link within {expires_minutes} minutes:\n\n{link}\n\nIf you did not request it, secure your account and ignore this message.",
        ),
        "password_reset": (
            f"Reset your {app_name} password",
            f"Reset your password using this single-use link within {expires_minutes} minutes:\n\n{link}\n\nIf you did not request this, do not open the link.",
        ),
        "organization_invite": (
            f"You were invited to a {app_name} workspace",
            f"Accept the workspace invitation within {expires_minutes} minutes:\n\n{link}",
        ),
        "security_alert": (
            f"{app_name} security alert",
            str(context.get("message") or "A security-sensitive change occurred on your account."),
        ),
        "payment_receipt": (
            f"Your {app_name} payment receipt {context.get('receipt_number') or ''}".strip(),
            str(context.get("message") or (
                f"Payment confirmed for {context.get('plan') or 'subscription'}.\n"
                f"Amount: {context.get('currency') or 'NGN'} {context.get('amount') or 0}\n"
                f"Reference: {context.get('payment_reference') or 'N/A'}"
            )),
        ),
    }
    subject, body = templates.get(str(template), (f"{app_name} notification", str(context.get("message") or "")))
    escaped = (
        body.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )
    html = f"<div style='font-family:system-ui,sans-serif;max-width:620px;margin:auto'><h2>{app_name}</h2><p>{escaped}</p><hr><small>Never share passwords, recovery codes, API keys, or trading credentials.</small></div>"
    return subject, body, html


async def queue_account_email(
    session: Any,
    *,
    recipient: str,
    template: str,
    context: Mapping[str, Any],
    user_id: int | None = None,
    idempotency_key: str | None = None,
) -> QueuedEmail:
    subject, plain_body, html_body = render_account_email(template, context)
    email_id = str(uuid4())
    await session.execute(
        text(
            "INSERT INTO email_outbox(email_id,user_id,recipient,template,subject,plain_body,html_body,context,idempotency_key,status,next_attempt_at) "
            "VALUES(:email_id,:uid,:recipient,:template,:subject,:plain,:html,CAST(:context AS JSONB),:idempotency,'pending',NOW()) "
            "ON CONFLICT(idempotency_key) WHERE idempotency_key IS NOT NULL DO NOTHING"
        ),
        {
            "email_id": email_id,
            "uid": user_id,
            "recipient": str(recipient).strip().lower(),
            "template": str(template)[:64],
            "subject": subject[:240],
            "plain": plain_body,
            "html": html_body,
            "context": json.dumps(dict(context), separators=(",", ":"), default=str),
            "idempotency": idempotency_key,
        },
    )
    return QueuedEmail(email_id=email_id, recipient=str(recipient).strip().lower(), template=str(template))


def _send_smtp(row: Mapping[str, Any]) -> None:
    host = str(os.getenv("SMTP_HOST") or "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    username = str(os.getenv("SMTP_USERNAME") or "").strip()
    password = str(os.getenv("SMTP_PASSWORD") or "")
    use_ssl = str(os.getenv("SMTP_USE_SSL", "0")).lower() in {"1", "true", "yes", "on"}
    use_starttls = str(os.getenv("SMTP_USE_STARTTLS", "1")).lower() in {"1", "true", "yes", "on"}
    timeout = max(3, int(os.getenv("SMTP_TIMEOUT_SECONDS", "15")))

    message = EmailMessage()
    message["From"] = _sender()
    message["To"] = str(row["recipient"])
    message["Subject"] = str(row["subject"])
    message.set_content(str(row["plain_body"]))
    if row.get("html_body"):
        message.add_alternative(str(row["html_body"]), subtype="html")

    context = ssl.create_default_context()
    if use_ssl:
        client_context = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
    else:
        client_context = smtplib.SMTP(host, port, timeout=timeout)
    with client_context as client:
        if not use_ssl and use_starttls:
            client.starttls(context=context)
        if username:
            client.login(username, password)
        client.send_message(message)


async def deliver_email_outbox_batch(limit: int = 25) -> dict[str, int]:
    """Claim and deliver pending messages. Safe to call repeatedly from one worker."""
    if not is_db_configured():
        return {"claimed": 0, "sent": 0, "failed": 0, "deferred": 0}
    if not _smtp_configured():
        return {"claimed": 0, "sent": 0, "failed": 0, "deferred": 1}

    async with get_session() as session:
        rows = (
            await session.execute(
                text(
                    "WITH claimed AS (SELECT email_id FROM email_outbox WHERE status IN ('pending','retry') "
                    "AND next_attempt_at<=NOW() ORDER BY created_at LIMIT :limit FOR UPDATE SKIP LOCKED) "
                    "UPDATE email_outbox e SET status='sending',attempt_count=attempt_count+1,updated_at=NOW() "
                    "FROM claimed WHERE e.email_id=claimed.email_id "
                    "RETURNING e.email_id,e.recipient,e.subject,e.plain_body,e.html_body,e.attempt_count"
                ),
                {"limit": max(1, min(int(limit), 100))},
            )
        ).mappings().all()
        await session.commit()

    sent = failed = 0
    for row in rows:
        try:
            await asyncio.to_thread(_send_smtp, row)
            status, last_error, delay = "sent", None, 0
            sent += 1
        except Exception as exc:  # noqa: BLE001
            attempts = int(row.get("attempt_count") or 1)
            terminal = attempts >= max(1, int(os.getenv("EMAIL_MAX_ATTEMPTS", "6")))
            status = "failed" if terminal else "retry"
            last_error = type(exc).__name__
            delay = min(3600, 30 * (2 ** min(attempts, 6)))
            failed += 1
            logger.warning("[email_outbox] delivery failed id=%s type=%s", row["email_id"], type(exc).__name__)
        async with get_session() as session:
            await session.execute(
                text(
                    "UPDATE email_outbox SET status=:status,last_error=:error,sent_at=CASE WHEN :status='sent' THEN NOW() ELSE sent_at END,"
                    "next_attempt_at=CASE WHEN :delay>0 THEN NOW()+(:delay * INTERVAL '1 second') ELSE next_attempt_at END,updated_at=NOW() "
                    "WHERE email_id=:email_id"
                ),
                {"status": status, "error": last_error, "delay": delay, "email_id": row["email_id"]},
            )
            await session.commit()
    return {"claimed": len(rows), "sent": sent, "failed": failed, "deferred": 0}


__all__ = ["QueuedEmail", "deliver_email_outbox_batch", "queue_account_email", "render_account_email"]
