"""Canonical subscription auto-renew cancellation.

Cancelling auto-renew never deletes payment evidence, refunds funds, or
immediately downgrades an active entitlement.  It disables recurring billing
at the provider when possible and always records the account preference so the
current paid period can expire naturally.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from sqlalchemy import select

from db.models import Subscription, User
from db.session import get_session

logger = logging.getLogger(__name__)


async def _disable_paystack_subscription(code: str) -> tuple[bool, int]:
    secret = str(os.getenv("PAYSTACK_SECRET_KEY") or "").strip()
    if not code or not secret:
        return False, 0
    try:
        max_retries = max(
            1,
            min(
                5,
                int(os.getenv("PAYSTACK_CANCEL_RETRY_ATTEMPTS", "3") or 3),
            ),
        )
    except Exception:
        max_retries = 3
    headers = {
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json",
    }
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                lookup = await client.get(
                    f"https://api.paystack.co/subscription/{code}",
                    headers=headers,
                )
                token = ""
                if lookup.status_code < 400:
                    token = str(
                        (lookup.json().get("data") or {}).get("email_token")
                        or ""
                    ).strip()
                response = await client.post(
                    "https://api.paystack.co/subscription/disable",
                    json={"code": code, "token": token},
                    headers=headers,
                )
                if response.status_code < 400:
                    return True, attempt
        except Exception:
            logger.warning(
                "[subscription_cancel] provider attempt failed attempt=%s",
                attempt,
                exc_info=True,
            )
    return False, max_retries


async def cancel_auto_renew_for_user(user_id: int) -> dict[str, Any]:
    """Disable future renewal for one canonical account.

    The DB preference is committed even when Paystack is unavailable so the
    application does not claim the user opted in to renewal.  A provider
    failure is returned explicitly for support/admin reconciliation.
    """
    canonical_id = int(user_id)
    async with get_session(
        priority="interactive",
        label="subscription.cancel_auto_renew",
        timeout_seconds=12.0,
    ) as session:
        user = (
            await session.execute(
                select(User).where(User.id == canonical_id).with_for_update().limit(1)
            )
        ).scalar_one_or_none()
        if user is None:
            await session.rollback()
            return {
                "success": False,
                "reason": "account_not_found",
                "gateway_cancelled": False,
                "retry_attempts": 0,
            }

        subscription = (
            await session.execute(
                select(Subscription)
                .where(
                    Subscription.user_id == canonical_id,
                    Subscription.status.in_(("active", "grace_period")),
                )
                .order_by(Subscription.expires_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if subscription is None:
            await session.rollback()
            return {
                "success": False,
                "reason": "no_active_paid_subscription",
                "tier": "free",
                "gateway_cancelled": False,
                "retry_attempts": 0,
            }

        tier = str(subscription.tier or user.tier or "free").strip().lower()
        sub_code = str(user.paystack_subscription_code or "").strip()
        gateway_cancelled, retry_attempts = await _disable_paystack_subscription(
            sub_code
        )
        user.auto_renew = False
        await session.commit()
        return {
            "success": True,
            "reason": "cancelled",
            "tier": tier,
            "auto_renew": False,
            "expires_at": subscription.expires_at,
            "gateway_cancelled": bool(gateway_cancelled),
            "retry_attempts": int(retry_attempts),
            "provider_follow_up_required": bool(
                sub_code and not gateway_cancelled
            ),
        }


async def cancel_auto_renew_for_telegram_user(
    telegram_user_id: int,
) -> dict[str, Any]:
    """Compatibility adapter for the Telegram command surface."""
    async with get_session(
        priority="interactive",
        label="subscription.resolve_telegram_cancel",
        timeout_seconds=8.0,
    ) as session:
        canonical_id = (
            await session.execute(
                select(User.id)
                .where(User.telegram_user_id == int(telegram_user_id))
                .limit(1)
            )
        ).scalar_one_or_none()
        await session.rollback()
    if canonical_id is None:
        return {
            "success": False,
            "reason": "account_not_found",
            "tier": "free",
            "gateway_cancelled": False,
            "retry_attempts": 0,
        }
    return await cancel_auto_renew_for_user(int(canonical_id))


__all__ = [
    "cancel_auto_renew_for_user",
    "cancel_auto_renew_for_telegram_user",
]
