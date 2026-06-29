from fastapi.testclient import TestClient
from unittest.mock import patch

from web.app import app, verify_api_key


client = TestClient(app)


def test_broker_permission_validation_rejects_withdrawal_enabled_key() -> None:
    res = client.post(
        "/broker/validate-api-permissions",
        json={
            "provider": "bybit",
            "trade": True,
            "read": True,
            "withdraw": True,
            "internal_transfer": False,
        },
    )
    assert res.status_code == 400
    body = res.json()
    assert body.get("ok") is False
    assert body.get("policy") == "trade_only_required"


def test_broker_permission_validation_accepts_trade_only_key() -> None:
    res = client.post(
        "/broker/validate-api-permissions",
        json={
            "provider": "binance",
            "trade": True,
            "read": True,
            "withdraw": False,
            "internal_transfer": False,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body.get("ok") is True
    assert body.get("policy") == "trade_only_required"


def test_broker_permission_validation_rejects_transfer_permission_string() -> None:
    res = client.post(
        "/broker/validate-api-permissions",
        json={
            "provider": "bybit",
            "trade": True,
            "read": True,
            "permissions": ["trade", "read", "transfer"],
        },
    )
    assert res.status_code == 400
    body = res.json()
    assert body.get("ok") is False
    assert body.get("policy") == "trade_only_required"


class _Session:
    def __init__(self):
        self.saved = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, _model, key):
        return self.saved.get(key)

    def add(self, row):
        self.saved[row.key] = row

    async def commit(self):
        return None


def test_exchange_link_requires_encryption_key() -> None:
    app.dependency_overrides[verify_api_key] = lambda: 123
    try:
        with patch("services.security.is_encryption_available", return_value=False):
            res = client.post(
                "/broker/exchange/link",
                headers={"Authorization": "Bearer test"},
                json={
                    "provider": "binance",
                    "api_key": "abcd1234efgh",
                    "api_secret": "secret123456",
                    "trade": True,
                    "read": True,
                    "withdraw": False,
                    "internal_transfer": False,
                },
            )
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 503


def test_exchange_link_stores_masked_encrypted_credentials() -> None:
    session = _Session()
    app.dependency_overrides[verify_api_key] = lambda: 123
    try:
        with (
            patch("web.app.get_session", return_value=session),
            patch("services.security.is_encryption_available", return_value=True),
            patch("services.security.encrypt_secret", side_effect=lambda value: f"enc:{value}"),
        ):
            res = client.post(
                "/broker/exchange/link",
                headers={"Authorization": "Bearer test"},
                json={
                    "provider": "bybit",
                    "api_key": "abcd1234efgh",
                    "api_secret": "secret123456",
                    "trade": True,
                    "read": True,
                    "withdraw": False,
                    "internal_transfer": False,
                    "sandbox": True,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["provider"] == "bybit"
    assert body["masked_key"] == "abcd...efgh"
    saved = session.saved["broker_exchange:123:bybit"].value
    assert saved["api_key_enc"] == "enc:abcd1234efgh"
    assert saved["api_secret_enc"] == "enc:secret123456"
    assert "api_secret" not in saved
