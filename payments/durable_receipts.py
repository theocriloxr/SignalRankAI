"""Durable, idempotent payment receipts for all SignalRankAI channels."""
from __future__ import annotations

import hashlib
import html
from datetime import datetime
from typing import Any

from sqlalchemy import select

from db.models import PaymentReceipt, Subscription, User
from services.platform.email_delivery import queue_account_email
from utils.timeutils import now_utc_naive

DISCLAIMER = "SignalRankAI provides trading intelligence; no profit or outcome is guaranteed."


def _receipt_number(reference: str, when: datetime) -> str:
    digest = hashlib.sha256(str(reference).encode("utf-8")).hexdigest()[:10].upper()
    return f"SR-{when.strftime('%Y%m%d')}-{digest}"


def _render_receipt(
    *,
    receipt_number: str,
    user_id: int,
    plan: str,
    amount: float,
    currency: str,
    payment_reference: str,
    subscription_start: datetime | None,
    subscription_end: datetime | None,
    payment_date: datetime,
) -> tuple[str, str]:
    lines = [
        "SIGNALRANKAI PAYMENT RECEIPT",
        f"Receipt: {receipt_number}",
        f"Account: {user_id}",
        f"Plan: {plan}",
        f"Amount: {currency} {amount:,.2f}",
        f"Payment reference: {payment_reference}",
        f"Payment date: {payment_date.isoformat()}",
        f"Subscription start: {subscription_start.isoformat() if subscription_start else 'N/A'}",
        f"Subscription end: {subscription_end.isoformat() if subscription_end else 'N/A'}",
        "Status: PAID",
        "Support: support@signalrank.ai",
        DISCLAIMER,
    ]
    plain = "\n".join(lines)
    body = "<br>".join(html.escape(line) for line in lines)
    rich = f"<div style='font-family:system-ui,sans-serif;max-width:680px;margin:auto'><h2>SignalRankAI</h2>{body}</div>"
    return plain, rich


async def create_payment_receipt(
    session: Any,
    *,
    user: User,
    subscription: Subscription,
    payment_reference: str,
    plan: str,
    amount_ngn: int,
    currency: str = "NGN",
    provider: str = "paystack",
    product_id: str | None = None,
) -> PaymentReceipt:
    existing = (
        await session.execute(
            select(PaymentReceipt).where(
                PaymentReceipt.provider == str(provider).lower(),
                PaymentReceipt.payment_reference == str(payment_reference),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    paid_at = now_utc_naive()
    receipt_number = _receipt_number(str(payment_reference), paid_at)
    plain, rich = _render_receipt(
        receipt_number=receipt_number,
        user_id=int(user.id),
        plan=str(plan),
        amount=float(amount_ngn),
        currency=str(currency).upper(),
        payment_reference=str(payment_reference),
        subscription_start=subscription.started_at,
        subscription_end=subscription.expires_at,
        payment_date=paid_at,
    )
    row = PaymentReceipt(
        receipt_number=receipt_number,
        user_id=int(user.id),
        provider=str(provider).lower(),
        payment_reference=str(payment_reference),
        plan=str(plan),
        amount=float(amount_ngn),
        currency=str(currency).upper(),
        status="paid",
        payment_date=paid_at,
        subscription_start=subscription.started_at,
        subscription_end=subscription.expires_at,
        text_body=plain,
        html_body=rich,
        meta={"verified_provider": True, "product_id": product_id},
    )
    session.add(row)
    await session.flush()

    email = str(user.primary_email or "").strip().lower()
    if email and user.email_verified_at is not None:
        await queue_account_email(
            session,
            recipient=email,
            template="payment_receipt",
            user_id=int(user.id),
            idempotency_key=f"payment_receipt:{provider}:{payment_reference}",
            context={
                "receipt_number": receipt_number,
                "plan": str(plan),
                "amount": float(amount_ngn),
                "currency": str(currency).upper(),
                "payment_reference": str(payment_reference),
                "subscription_end": subscription.expires_at.isoformat() if subscription.expires_at else None,
                "message": plain,
            },
        )
    return row


__all__ = ["create_payment_receipt"]
