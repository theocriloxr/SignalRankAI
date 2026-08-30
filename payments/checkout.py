"""Canonical SignalRankAI Paystack checkout initialization.

The server resolves price and entitlement metadata from the database catalogue.
Credentials never activate execution and clients never provide a trusted amount.
"""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import httpx

from payments.catalog import CheckoutProduct
from payments.paystack_policy import evaluate_paystack_operation


class CheckoutInitializationError(RuntimeError):
    pass


def _trusted_callback_url() -> str | None:
    explicit = str(os.getenv("PAYSTACK_CALLBACK_URL") or "").strip()
    if explicit:
        return explicit
    base = str(os.getenv("APP_BASE_URL") or "").strip().rstrip("/")
    return f"{base}/billing/complete" if base else None


def _plan_code(product: CheckoutProduct) -> str | None:
    exact = "PAYSTACK_" + product.product_id.upper().replace("-", "_") + "_PLAN_CODE"
    tier = "PAYSTACK_" + product.tier.upper() + "_PLAN_CODE"
    return str(os.getenv(exact) or os.getenv(tier) or "").strip() or None


async def initialize_paystack_checkout(
    *,
    product: CheckoutProduct,
    canonical_user_id: int,
    email: str,
    telegram_user_id: int | None = None,
    timeout_seconds: float = 20.0,
) -> dict[str, Any]:
    secret = str(os.getenv("PAYSTACK_SECRET_KEY") or "").strip()
    if not secret:
        raise CheckoutInitializationError("paystack_secret_missing")
    normalized_email = str(email or "").strip().lower()
    if "@" not in normalized_email:
        raise CheckoutInitializationError("verified_email_required")

    decision = evaluate_paystack_operation(
        telegram_user_id=telegram_user_id,
        canonical_user_id=int(canonical_user_id),
        amount_ngn=product.price_ngn,
    )
    if not decision.allowed:
        raise CheckoutInitializationError(f"paystack_policy_blocked:{decision.reason}")

    metadata: dict[str, Any] = {
        "user_id": int(canonical_user_id),
        "product_id": product.product_id,
        "tier": product.tier,
        "duration_days": product.duration_days,
        "amount_ngn": product.price_ngn,
        "currency": product.currency,
        "paystack_mode": decision.mode,
        "source": "unified_platform",
    }
    if telegram_user_id is not None:
        metadata["telegram_user_id"] = int(telegram_user_id)

    payload: dict[str, Any] = {
        "email": normalized_email,
        "amount": int(product.price_kobo),
        "currency": product.currency,
        "metadata": metadata,
    }
    callback = _trusted_callback_url()
    if callback:
        payload["callback_url"] = callback
    plan_code = _plan_code(product)
    if plan_code:
        payload["plan"] = plan_code
        metadata["plan_code"] = plan_code

    base_url = str(os.getenv("PAYSTACK_BASE_URL") or "https://api.paystack.co").rstrip("/")
    async with httpx.AsyncClient(timeout=max(3.0, float(timeout_seconds))) as client:
        response = await client.post(
            f"{base_url}/transaction/initialize",
            json=payload,
            headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
        )
    if response.status_code >= 400:
        raise CheckoutInitializationError(f"paystack_initialize_http_{response.status_code}")
    result = response.json()
    data = result.get("data") if isinstance(result, dict) else None
    if not result.get("status") or not isinstance(data, dict):
        raise CheckoutInitializationError("paystack_initialize_rejected")
    authorization_url = str(data.get("authorization_url") or "").strip()
    reference = str(data.get("reference") or "").strip()
    access_code = str(data.get("access_code") or "").strip()
    if not authorization_url or not reference:
        raise CheckoutInitializationError("paystack_initialize_incomplete")
    parsed = urlparse(authorization_url)
    hostname = str(parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (hostname == "paystack.com" or hostname.endswith(".paystack.com")):
        raise CheckoutInitializationError("paystack_authorization_url_invalid")
    return {
        "authorization_url": authorization_url,
        "reference": reference,
        "access_code": access_code or None,
        "product_id": product.product_id,
        "tier": product.tier,
        "duration_days": product.duration_days,
        "amount_ngn": product.price_ngn,
        "currency": product.currency,
    }


__all__ = ["CheckoutInitializationError", "initialize_paystack_checkout"]
