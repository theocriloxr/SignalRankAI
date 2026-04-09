from fastapi.testclient import TestClient

from web.app import app


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
