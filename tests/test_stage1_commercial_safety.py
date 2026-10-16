from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError


@pytest.mark.parametrize("field", ["platform_terms_accepted", "privacy_acknowledged", "age_eligibility_confirmed"])
async def test_registration_rejects_missing_consent_before_account_write(monkeypatch, field):
    from web import platform_api as api
    monkeypatch.setattr(api, "is_db_configured", lambda: True)
    fields = dict(email="stage1@example.invalid", password="test-password-12345",
                  platform_terms_accepted=True, privacy_acknowledged=True, age_eligibility_confirmed=True)
    fields[field] = False
    def no_session(**kwargs):
        raise AssertionError("A rejected consent must not reach account persistence")
    monkeypatch.setattr(api, "get_session", no_session)
    with pytest.raises(HTTPException) as error:
        await api.register(api.RegisterRequest(**fields), SimpleNamespace(), SimpleNamespace())
    assert error.value.status_code == 422


@pytest.mark.parametrize("value", ["true", "yes", 1, [], None])
def test_consent_cannot_be_created_by_boolean_coercion(value):
    from web.platform_api import RegisterRequest, CheckoutCreateRequest
    with pytest.raises(ValidationError):
        RegisterRequest(email="stage1@example.invalid", password="test-password-12345", platform_terms_accepted=value)
    with pytest.raises(ValidationError):
        CheckoutCreateRequest(product_id="premium-monthly", recurring_acknowledged=value)


@pytest.mark.parametrize("body", [{"status": False}, {"status": "true"}, {}, []])
async def test_http_success_is_not_provider_cancellation_proof(monkeypatch, body):
    from services import subscription_cancellation as service
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "test-placeholder")
    monkeypatch.setenv("PAYSTACK_CANCEL_RETRY_ATTEMPTS", "1")
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, *args, **kwargs):
            return SimpleNamespace(status_code=200, json=lambda: {"data": {"email_token": "test"}})
        async def post(self, *args, **kwargs):
            return SimpleNamespace(status_code=200, json=lambda: body)
    monkeypatch.setattr(service.httpx, "AsyncClient", Client)
    assert await service._disable_paystack_subscription("test-code") == (False, 1)


@pytest.mark.parametrize("confirmed,changed", [(False, False), (True, True), (True, False)])
async def test_pending_or_different_subscription_is_not_reported_cancelled(monkeypatch, confirmed, changed):
    from services import subscription_cancellation as service
    before = SimpleNamespace(auto_renew=True, paystack_subscription_code="old", tier="premium")
    after = SimpleNamespace(auto_renew=True, paystack_subscription_code="new" if changed else "old")
    sub = SimpleNamespace(tier="premium", expires_at=None)
    class Session:
        def __init__(self, rows): self.rows = iter(rows)
        async def execute(self, *args):
            row = next(self.rows)
            return SimpleNamespace(scalar_one_or_none=lambda: row)
        async def rollback(self): pass
        async def commit(self): pass
    sessions = iter([Session([before, sub]), Session([after])])
    @asynccontextmanager
    async def get_session(**kwargs): yield next(sessions)
    monkeypatch.setattr(service, "get_session", get_session)
    monkeypatch.setattr(service, "_disable_paystack_subscription", AsyncMock(return_value=(confirmed, 1)))
    result = await service.cancel_auto_renew_for_user(5)
    pending = not confirmed or changed
    assert result["provider_follow_up_required"] is pending
    assert result["auto_renew"] is pending
    assert after.auto_renew is pending
    assert result["reason"] == ("provider_follow_up_required" if pending else "cancelled")
