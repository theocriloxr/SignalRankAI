"""Idempotent confirmed-payment receipt service.

Receipt generation is deliberately separate from payment verification: callers
must pass ``verified=True`` and a successful status.  The in-memory store makes
the contract testable offline; ``save_receipt`` can be replaced by the DB
repository in a deployment.
"""

from __future__ import annotations

import html
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


DISCLAIMER = "SignalRankAI provides trading intelligence; no profit or outcome is guaranteed."


@dataclass(frozen=True, slots=True)
class PaymentReceipt:
    receipt_number: str
    user_id: int
    plan: str
    amount: float
    currency: str
    payment_reference: str
    provider: str
    payment_date: str
    billing_period: str
    subscription_start: str | None
    subscription_end: str | None
    status: str
    text_body: str
    html_body: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReceiptService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_reference: dict[tuple[str, str], PaymentReceipt] = {}

    def create_confirmed_receipt(
        self,
        *,
        user_id: int,
        plan: str,
        amount: float,
        currency: str = "NGN",
        payment_reference: str,
        provider: str = "paystack",
        billing_period: str = "monthly",
        subscription_start: str | None = None,
        subscription_end: str | None = None,
        verified: bool = False,
        status: str = "paid",
    ) -> PaymentReceipt:
        if not verified:
            raise ValueError("receipt_requires_verified_payment")
        if str(status).lower() not in {"paid", "success", "successful"}:
            raise ValueError("receipt_requires_success_status")
        reference = str(payment_reference or "").strip()
        if not reference:
            raise ValueError("payment_reference_required")
        key = (str(provider).lower(), reference)
        with self._lock:
            existing = self._by_reference.get(key)
            if existing:
                return existing
            now = datetime.now(timezone.utc).isoformat()
            receipt_number = "SR-" + datetime.now(timezone.utc).strftime("%Y%m%d") + "-" + str(len(self._by_reference) + 1).zfill(6)
            text_body = "\n".join(
                (
                    "SIGNALRANKAI PAYMENT RECEIPT",
                    f"Receipt: {receipt_number}",
                    f"User: {int(user_id)}",
                    f"Plan: {plan}",
                    f"Amount: {currency.upper()} {float(amount):,.2f}",
                    f"Payment reference: {reference}",
                    f"Provider: {provider}",
                    f"Payment date: {now}",
                    f"Billing period: {billing_period}",
                    f"Subscription start: {subscription_start or 'N/A'}",
                    f"Subscription end: {subscription_end or 'N/A'}",
                    "Status: PAID",
                    "Support: support@signalrank.ai",
                    DISCLAIMER,
                )
            )
            html_body = "<br>".join(html.escape(line) for line in text_body.splitlines())
            receipt = PaymentReceipt(receipt_number, int(user_id), str(plan), float(amount), str(currency).upper(), reference, str(provider).lower(), now, str(billing_period), subscription_start, subscription_end, "paid", text_body, html_body)
            self._by_reference[key] = receipt
            return receipt

    def create_refund_credit_note(self, receipt: PaymentReceipt, *, refund_reference: str) -> PaymentReceipt:
        return PaymentReceipt(
            receipt_number=f"{receipt.receipt_number}-CR",
            user_id=receipt.user_id,
            plan=receipt.plan,
            amount=-abs(receipt.amount),
            currency=receipt.currency,
            payment_reference=str(refund_reference),
            provider=receipt.provider,
            payment_date=datetime.now(timezone.utc).isoformat(),
            billing_period=receipt.billing_period,
            subscription_start=receipt.subscription_start,
            subscription_end=receipt.subscription_end,
            status="refunded",
            text_body=f"REFUND CREDIT NOTE\nOriginal receipt: {receipt.receipt_number}\nReference: {refund_reference}\nAmount: -{receipt.currency} {abs(receipt.amount):,.2f}\n{DISCLAIMER}",
            html_body="",
        )

    def get(self, payment_reference: str, *, provider: str = "paystack") -> PaymentReceipt | None:
        return self._by_reference.get((str(provider).lower(), str(payment_reference)))

    def list_for_user(self, user_id: int) -> list[PaymentReceipt]:
        return [receipt for receipt in self._by_reference.values() if receipt.user_id == int(user_id)]


receipt_service = ReceiptService()

__all__ = ["DISCLAIMER", "PaymentReceipt", "ReceiptService", "receipt_service"]
