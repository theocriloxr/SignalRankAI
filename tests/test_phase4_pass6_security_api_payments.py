"""Pass 6 contracts for API, broker, and payment security boundaries."""

import hashlib
import hmac

from fastapi.testclient import TestClient


def test_web_app_is_asgi_and_exposes_versioned_api() -> None:
    from web.app import app

    client = TestClient(app)
    response = client.post(
        "/broker/validate-api-permissions",
        json={
            "provider": "binance",
            "trade": True,
            "read": True,
            "withdraw": False,
            "internal_transfer": False,
        },
    )
    assert response.status_code == 200
    assert response.json()["policy"] == "trade_only_required"


def test_broker_permission_validation_rejects_unknown_provider() -> None:
    from web.app import app

    response = TestClient(app).post(
        "/broker/validate-api-permissions",
        json={
            "provider": "unknown",
            "trade": True,
            "read": True,
            "withdraw": False,
            "internal_transfer": False,
        },
    )
    assert response.status_code == 400
    assert response.json()["ok"] is False


def test_missing_api_key_is_401() -> None:
    from web.app import app

    response = TestClient(app).post(
        "/broker/exchange/link",
        json={
            "provider": "binance",
            "api_key": "abcd1234",
            "api_secret": "secret1234",
            "trade": True,
            "read": True,
        },
    )
    assert response.status_code == 401


def test_payments_are_disabled_without_explicit_flag(monkeypatch) -> None:
    from web.app import _payments_enabled

    monkeypatch.delenv("PAYMENTS_ENABLED", raising=False)
    assert _payments_enabled() is False


def test_paystack_signature_uses_runtime_secret(monkeypatch) -> None:
    from payments.paystack import verify_signature

    body = b'{"event":"charge.success"}'
    monkeypatch.setenv("PAYSTACK_WEBHOOK_SECRET", "runtime-secret")
    signature = hmac.new(b"runtime-secret", body, hashlib.sha512).hexdigest()
    assert verify_signature(body, signature) is True
    assert verify_signature(body, "bad") is False


def test_secret_redaction_does_not_leak_nested_values() -> None:
    from core.security import redact_secrets

    result = redact_secrets({"nested": [{"api_secret": "do-not-log"}], "safe": "ok"})
    assert result == {"nested": [{"api_secret": "<redacted>"}], "safe": "ok"}
