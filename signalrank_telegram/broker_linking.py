"""Safe Telegram handoff into the first-party Broker Hub.

Telegram is an interaction surface, not a broker-secret collection channel.
Broker credentials must be entered only through the authenticated first-party
app/secure provider-link flow.
"""
from __future__ import annotations

import os
from urllib.parse import quote

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

from db.session import get_session
from services.platform.identity import create_telegram_activation


def _app_base_url() -> str:
    raw = str(
        os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or os.getenv("APP_BASE_URL")
        or os.getenv("STAGING_APP_BASE_URL")
        or os.getenv("WEBHOOK_BASE_URL")
        or ""
    ).strip().rstrip("/")
    if raw and not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    return raw


async def send_secure_broker_hub_link(update: Update) -> bool:
    """Issue a short-lived first-party app link for broker connection setup."""
    if update.effective_user is None or update.message is None:
        return False

    base_url = _app_base_url()
    if not base_url:
        await update.message.reply_text(
            "Secure broker linking is temporarily unavailable because the app URL "
            "is not configured. Broker passwords must not be sent in Telegram."
        )
        return False

    tg = update.effective_user
    display_name = " ".join(
        filter(None, [getattr(tg, "first_name", None), getattr(tg, "last_name", None)])
    ).strip() or None

    async with get_session(
        priority="interactive",
        label="telegram.secure_broker_handoff",
        timeout_seconds=6.0,
    ) as session:
        activation = await create_telegram_activation(
            session,
            telegram_user_id=int(tg.id),
            username=getattr(tg, "username", None),
            display_name=display_name,
        )
        await session.commit()

    activation_url = f"{base_url}/activate?token={quote(str(activation.token), safe='')}"
    await update.message.reply_text(
        "🔐 *Secure broker linking*\n\n"
        "For security, SignalRankAI does **not** accept broker passwords in Telegram. "
        "Open the first-party app, then go to *Broker Hub → MetaTrader* and use the "
        "secure provider link or encrypted credential form.\n\n"
        "Linking an account never enables execution. After linking, run `/verifybroker` "
        "for read-only provider verification. For a DEMO account, use *Prepare DEMO "
        "certification* in Broker Hub; execution remains OFF until separately enabled "
        "after policy and reconciliation checks.\n\n"
        f"One-time code: `{activation.code}`\n"
        f"Expires: {activation.expires_at.strftime('%H:%M UTC')}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Open secure Broker Hub", url=activation_url)]]
        ),
    )
    return True


__all__ = ["send_secure_broker_hub_link"]
