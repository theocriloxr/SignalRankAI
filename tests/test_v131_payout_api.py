from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from web.app import app, verify_api_key

client = TestClient(app)


def _auth(user_id: int = 9001) -> None:
    app.dependency_overrides[verify_api_key] = lambda: user_id


def _clear() -> None:
    app.dependency_overrides.clear()


def test_ordinary_user_cannot_create_disbursement() -> None:
    _auth()
    try:
        with patch("web.app._is_admin_user", new=AsyncMock(return_value=False)):
            res = client.post("/payout/request", json={
                "recipient_telegram_user_id": 123,
                "amount_ngn": 5000,
                "reason": "approved refund",
            })
    finally:
        _clear()
    assert res.status_code == 403


def test_admin_can_create_disbursement_for_verified_recipient() -> None:
    _auth()
    row = SimpleNamespace(reference="srp_ref", status="requested", amount_kobo=500000)
    try:
        with (
            patch("web.app._is_admin_user", new=AsyncMock(return_value=True)),
            patch("payments.payout_service.create_payout_request", new=AsyncMock(return_value=row)) as create,
        ):
            res = client.post("/payout/request", json={
                "recipient_telegram_user_id": 123,
                "amount_ngn": 5000,
                "reason": "approved refund",
            })
    finally:
        _clear()
    assert res.status_code == 200
    assert res.json()["reference"] == "srp_ref"
    create.assert_awaited_once_with(
        recipient_telegram_user_id=123,
        requested_by_telegram_id=9001,
        amount_ngn=5000.0,
        reason="approved refund",
    )


def test_admin_can_finalize_otp_gated_transfer(monkeypatch) -> None:
    _auth()
    result = SimpleNamespace(reference="srp_ref", status="submitted", transfer_code="TRF_1")
    monkeypatch.setenv("PAYSTACK_TRANSFER_OTP_FLOW_ENABLED", "1")
    try:
        with (
            patch("web.app._is_admin_user", new=AsyncMock(return_value=True)),
            patch("payments.payout_service.finalize_payout", new=AsyncMock(return_value=result)) as finalize,
        ):
            res = client.post("/payout/finalize", json={"reference": "srp_ref", "otp": "123456"})
    finally:
        _clear()
    assert res.status_code == 200
    finalize.assert_awaited_once_with(reference="srp_ref", otp="123456", approver_telegram_id=9001)


def test_admin_can_verify_transfer() -> None:
    _auth()
    try:
        with (
            patch("web.app._is_admin_user", new=AsyncMock(return_value=True)),
            patch("payments.payout_service.verify_transfer", new=AsyncMock(return_value={"status": "success"})),
        ):
            res = client.get("/payout/verify/srp_ref")
    finally:
        _clear()
    assert res.status_code == 200
    assert res.json()["provider"]["status"] == "success"
