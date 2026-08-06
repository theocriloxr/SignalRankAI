from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


class _MappingResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        if self._value is None:
            raise AssertionError("expected scalar")
        return self._value


@pytest.mark.asyncio
async def test_catalogue_resolves_server_price_and_rejects_contact_sales():
    from payments.catalog import ProductCatalogueError, resolve_checkout_product

    class Session:
        def __init__(self, price):
            self.calls = 0
            self.price = price

        async def execute(self, _statement, _params):
            self.calls += 1
            if self.calls == 1:
                return _MappingResult(
                    {
                        "product_id": "premium_monthly",
                        "tier": "PREMIUM",
                        "display_name": "Premium Monthly",
                        "duration_days": 30,
                        "active": True,
                    }
                )
            return _MappingResult({"currency": "NGN", "price_kobo": self.price})

    product = await resolve_checkout_product(Session(2_400_000), "premium_monthly")
    assert product.price_ngn == 24_000
    assert product.tier == "premium"
    assert product.duration_days == 30

    with pytest.raises(ProductCatalogueError, match="contact_sales"):
        await resolve_checkout_product(Session(0), "professional_monthly")


@pytest.mark.asyncio
async def test_app_only_checkout_uses_canonical_identity_and_server_amount(monkeypatch):
    from payments.catalog import CheckoutProduct
    from payments.checkout import initialize_paystack_checkout

    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_test_fixture")
    monkeypatch.setenv("APP_BASE_URL", "https://app.signalrank.ai")
    captured = {}

    class Response:
        status_code = 200

        def json(self):
            return {
                "status": True,
                "data": {
                    "authorization_url": "https://checkout.paystack.com/secure",
                    "reference": "sr-app-only-1",
                    "access_code": "access",
                },
            }

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, *, json, headers):
            captured.update({"url": url, "json": json, "headers": headers})
            return Response()

    monkeypatch.setattr("payments.checkout.httpx.AsyncClient", Client)
    result = await initialize_paystack_checkout(
        product=CheckoutProduct("premium_monthly", "premium", "Premium Monthly", 30, "NGN", 2_400_000),
        canonical_user_id=42,
        email="verified@example.com",
        telegram_user_id=None,
    )
    assert result["amount_ngn"] == 24_000
    assert captured["json"]["amount"] == 2_400_000
    assert captured["json"]["metadata"]["user_id"] == 42
    assert "telegram_user_id" not in captured["json"]["metadata"]
    assert captured["json"]["callback_url"] == "https://app.signalrank.ai/billing/complete"


def test_guarded_live_staging_accepts_allowlisted_canonical_user(monkeypatch):
    from payments.paystack_policy import PAYSTACK_LIVE_STAGING_ACK_VALUE, evaluate_paystack_operation

    env = {
        "APP_ENV": "staging",
        "PAYSTACK_SECRET_KEY": "sk_live_fixture",
        "PAYSTACK_PUBLIC_KEY": "pk_live_fixture",
        "FULL_SYSTEM_STAGING_TEST_ACTIVE": "1",
        "PAYSTACK_LIVE_STAGING_ENABLED": "1",
        "PAYSTACK_LIVE_STAGING_ACK": PAYSTACK_LIVE_STAGING_ACK_VALUE,
        "PAYSTACK_LIVE_STAGING_ALLOWED_CANONICAL_USER_IDS": "42",
    }
    decision = evaluate_paystack_operation(canonical_user_id=42, amount_ngn=24_000, environ=env)
    assert decision.allowed is True
    assert decision.reason == "guarded_live_staging"


@pytest.mark.asyncio
async def test_charge_success_activates_app_only_canonical_user(monkeypatch):
    from payments.catalog import CheckoutProduct
    from payments.paystack import process_event

    product = CheckoutProduct("premium_monthly", "premium", "Premium Monthly", 30, "NGN", 2_400_000)
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_test_fixture")

    catalog_session = SimpleNamespace(rollback=AsyncMock())
    payment_user = SimpleNamespace(
        id=42,
        telegram_user_id=None,
        primary_email="verified@example.com",
        email_verified_at=SimpleNamespace(),
    )
    subscription = SimpleNamespace(started_at=None, expires_at=None)

    class PaymentSession:
        def __init__(self):
            self.execute_calls = 0
            self.commit = AsyncMock()

        async def execute(self, _statement):
            self.execute_calls += 1
            return _ScalarResult(None if self.execute_calls == 1 else payment_user)

    payment_session = PaymentSession()
    sessions = iter([catalog_session, payment_session])

    @asynccontextmanager
    async def fake_get_session(*args, **kwargs):
        yield next(sessions)

    record = AsyncMock()
    activate = AsyncMock(return_value=subscription)
    receipt = AsyncMock()
    monkeypatch.setattr("db.session.get_session", fake_get_session)
    monkeypatch.setattr("payments.catalog.resolve_checkout_product", AsyncMock(return_value=product))
    monkeypatch.setattr("db.pg_features.record_payment_event", record)
    monkeypatch.setattr("db.repository.activate_subscription", activate)
    monkeypatch.setattr("payments.durable_receipts.create_payment_receipt", receipt)

    result = await process_event(
        {
            "event": "charge.success",
            "data": {
                "reference": "app-only-reference",
                "amount": 2_400_000,
                "currency": "NGN",
                "metadata": {
                    "user_id": 42,
                    "product_id": "premium_monthly",
                    "amount_ngn": 24_000,
                },
            },
        }
    )
    assert result["processed"] is True
    assert record.await_args.kwargs["user_id"] == 42
    assert record.await_args.kwargs["telegram_user_id"] is None
    assert activate.await_args.kwargs["user_id"] == 42
    assert receipt.await_count == 1
    assert payment_session.commit.await_count == 1


def test_receipt_email_template_is_supported():
    from services.platform.email_delivery import render_account_email

    subject, plain, html = render_account_email(
        "payment_receipt",
        {
            "receipt_number": "SR-1",
            "plan": "premium_monthly",
            "currency": "NGN",
            "amount": 24_000,
            "payment_reference": "ref",
            "message": "Paid successfully",
        },
    )
    assert "SR-1" in subject
    assert "Paid successfully" in plain
    assert "Paid successfully" in html
