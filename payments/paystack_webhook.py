"""
SignalRankAI — Paystack Webhook Handler (PERFECTED)

Handles Paystack webhook events:
  subscription.create   → upgrade user tier
  charge.success        → extra signal credits
  subscription.disable  → downgrade to free

Security:
  - HMAC-SHA512 signature verification (every request)
  - IP address whitelist (Paystack servers only)
  - Idempotency via reference tracking (no double-processing)
  - Raw body read BEFORE JSON parsing (signature uses raw bytes)

Registered in web/app.py as: POST /webhook/paystack
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/webhook/paystack")
async def paystack_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receive and process Paystack webhook events.
    
    Security flow:
    1. Check request IP against Paystack whitelist
    2. Read raw body bytes (MUST be before await request.json())
    3. Verify HMAC-SHA512 signature using raw bytes
    4. Parse event and dispatch to processor
    5. Return 200 immediately (background processing)
    """
    from payments.paystack import (
        verify_webhook_signature,
        PAYSTACK_WEBHOOK_IP_WHITELIST,
    )

    # ── IP whitelist check ────────────────────────────────────────────────────
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.headers.get("X-Real-IP", "").strip()
        or (request.client.host if request.client else "")
    )

    # Skip IP check in dev/test mode
    import os
    dev_mode = os.getenv("DEV_MODE", "0").lower() in ("1", "true", "yes")
    if not dev_mode and PAYSTACK_WEBHOOK_IP_WHITELIST and client_ip not in PAYSTACK_WEBHOOK_IP_WHITELIST:
        logger.warning("[paystack_webhook] Rejected request from IP: %s", client_ip)
        raise HTTPException(status_code=403, detail="Forbidden")

    # ── Read raw body (MUST happen before any JSON parsing) ───────────────────
    raw_body = await request.body()

    # ── Signature verification ────────────────────────────────────────────────
    signature = request.headers.get("X-Paystack-Signature", "")
    if not verify_webhook_signature(raw_body, signature):
        logger.warning("[paystack_webhook] Invalid signature from IP: %s", client_ip)
        raise HTTPException(status_code=401, detail="Invalid signature")

    # ── Parse event ───────────────────────────────────────────────────────────
    try:
        body = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        logger.error("[paystack_webhook] Failed to parse JSON: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event = str(body.get("event") or "")
    data  = body.get("data") or {}

    logger.info("[paystack_webhook] Received event: %s", event)

    # ── Dispatch event processing in background ───────────────────────────────
    # Return 200 immediately — Paystack retries if we don't respond quickly
    background_tasks.add_task(_process_event, event, data)

    return {"status": "ok"}


async def _process_event(event: str, data: dict) -> None:
    """Process a Paystack webhook event."""
    try:
        from payments.paystack import (
            process_subscription_create,
            process_charge_success,
            process_subscription_disable,
        )

        if event == "subscription.create":
            success = await process_subscription_create(data)
            if not success:
                logger.error("[paystack_webhook] subscription.create processing failed")

        elif event in ("charge.success", "invoice.payment_failed"):
            if event == "charge.success":
                success = await process_charge_success(data)
                if not success:
                    logger.error("[paystack_webhook] charge.success processing failed")
            else:
                # Invoice payment failed — notify user
                await _handle_payment_failed(data)

        elif event == "subscription.disable":
            success = await process_subscription_disable(data)
            if not success:
                logger.error("[paystack_webhook] subscription.disable processing failed")

        elif event == "subscription.not_renew":
            # Subscription scheduled to not renew — warn user
            await _handle_subscription_not_renew(data)

        elif event == "customeridentification.success":
            logger.debug("[paystack_webhook] Customer identified: %s", data.get("customer_id"))

        else:
            logger.debug("[paystack_webhook] Unhandled event: %s", event)

    except Exception as exc:
        logger.exception("[paystack_webhook] _process_event failed for %s: %s", event, exc)


async def _handle_payment_failed(data: dict) -> None:
    """Notify user when an invoice payment fails."""
    try:
        email = str((data.get("customer") or {}).get("email") or "")
        if not email:
            return

        from payments.paystack import _lookup_user_by_email
        telegram_user_id = await _lookup_user_by_email(email)
        if not telegram_user_id:
            return

        from signalrank_telegram.bot import _send_message_with_retry, _require_telegram_token
        from telegram import Bot

        bot = Bot(token=_require_telegram_token())
        await _send_message_with_retry(
            bot,
            chat_id=int(telegram_user_id),
            text=(
                "⚠️ <b>Payment Failed</b>\n\n"
                "Your subscription renewal payment could not be processed.\n\n"
                "Please update your payment method to maintain access.\n"
                "→ /upgrade to resubscribe"
            ),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.debug("[paystack_webhook] payment failed notification error: %s", exc)


async def _handle_subscription_not_renew(data: dict) -> None:
    """Notify user their subscription will not renew."""
    try:
        email = str((data.get("customer") or {}).get("email") or "")
        if not email:
            return

        from payments.paystack import _lookup_user_by_email
        telegram_user_id = await _lookup_user_by_email(email)
        if not telegram_user_id:
            return

        from signalrank_telegram.bot import _send_message_with_retry, _require_telegram_token
        from telegram import Bot

        next_payment = data.get("next_payment_date", "")

        bot = Bot(token=_require_telegram_token())
        await _send_message_with_retry(
            bot,
            chat_id=int(telegram_user_id),
            text=(
                "📋 <b>Subscription Update</b>\n\n"
                "Your subscription is set to expire and will not auto-renew.\n"
                + (f"\nExpiry date: <b>{next_payment}</b>\n" if next_payment else "\n") +
                "Use /upgrade to resubscribe and maintain access."
            ),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.debug("[paystack_webhook] not_renew notification error: %s", exc)


__all__ = ["router"]