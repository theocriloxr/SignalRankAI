"""DB-backed, owner-approved Paystack payout service.

Paper PnL is never cash. A payout must reference a verified beneficiary, be
approved by an owner/admin, and use a unique provider reference.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select

from core.financial_activation import evaluate_financial_activation
from db.models import PayoutAccountRecord, PayoutRequestRecord, User
from db.session import get_session
from services.security import decrypt_secret, encrypt_secret
from utils.timeutils import now_utc_naive


class PayoutError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PayoutSubmission:
    reference: str
    status: str
    transfer_code: str | None


def _secret() -> str:
    value = str(os.getenv("PAYSTACK_SECRET_KEY") or "").strip().strip('"').strip("'")
    if not value.startswith("sk_live_"):
        raise PayoutError("paystack_live_secret_required")
    return value


async def _paystack(method: str, path: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {_secret()}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.request(method, f"https://api.paystack.co{path}", params=params, json=body, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise PayoutError(f"paystack_transport:{type(exc).__name__}") from exc
    if not isinstance(payload, dict) or payload.get("status") is not True:
        raise PayoutError(str((payload or {}).get("message") or "paystack_rejected")[:180])
    return dict(payload.get("data") or {})


async def verify_and_store_payout_account(
    *,
    telegram_user_id: int,
    account_number: str,
    bank_code: str,
    bank_name: str,
    currency: str = "NGN",
) -> PayoutAccountRecord:
    number = re.sub(r"\D", "", str(account_number or ""))
    code = re.sub(r"[^0-9A-Za-z_-]", "", str(bank_code or ""))
    currency = str(currency or "NGN").upper()
    if currency != "NGN" or len(number) != 10 or not code:
        raise PayoutError("invalid_ngn_bank_account")
    resolved = await _paystack("GET", "/bank/resolve", params={"account_number": number, "bank_code": code})
    account_name = str(resolved.get("account_name") or "").strip()
    if not account_name:
        raise PayoutError("account_resolution_failed")
    recipient = await _paystack("POST", "/transferrecipient", body={
        "type": "nuban", "name": account_name, "account_number": number,
        "bank_code": code, "currency": currency,
        "description": "SignalRankAI verified payout beneficiary",
    })
    recipient_code = str(recipient.get("recipient_code") or "").strip()
    encrypted_number = encrypt_secret(number)
    encrypted_recipient = encrypt_secret(recipient_code)
    if not encrypted_number or not encrypted_recipient or not recipient_code:
        raise PayoutError("payout_credential_encryption_failed")

    async with get_session(label="payout.account", timeout_seconds=10.0) as session:
        user = (await session.execute(select(User).where(User.telegram_user_id == int(telegram_user_id)))).scalar_one_or_none()
        if user is None:
            raise PayoutError("user_not_found")
        row = (await session.execute(select(PayoutAccountRecord).where(
            PayoutAccountRecord.user_id == int(user.id), PayoutAccountRecord.currency == currency,
        ).with_for_update())).scalar_one_or_none()
        if row is None:
            row = PayoutAccountRecord(
                user_id=int(user.id), currency=currency, bank_code=code, bank_name=str(bank_name or recipient.get("details", {}).get("bank_name") or ""),
                account_number_encrypted=encrypted_number, account_last4=number[-4:], account_name=account_name,
                recipient_code_encrypted=encrypted_recipient, verified=True, verified_at=now_utc_naive(),
            )
            session.add(row)
        else:
            row.bank_code = code
            row.bank_name = str(bank_name or row.bank_name)
            row.account_number_encrypted = encrypted_number
            row.account_last4 = number[-4:]
            row.account_name = account_name
            row.recipient_code_encrypted = encrypted_recipient
            row.verified = True
            row.verified_at = now_utc_naive()
            row.updated_at = now_utc_naive()
        await session.commit()
        await session.refresh(row)
        return row


async def create_payout_request(
    *, recipient_telegram_user_id: int, requested_by_telegram_id: int, amount_ngn: float, reason: str,
) -> PayoutRequestRecord:
    amount_kobo = int(round(float(amount_ngn) * 100))
    minimum = int(float(os.getenv("PAYOUT_MINIMUM_NGN", "1000")) * 100)
    maximum = int(float(os.getenv("PAYOUT_MAXIMUM_NGN", "1000000")) * 100)
    if amount_kobo < minimum or amount_kobo > maximum:
        raise PayoutError("payout_amount_outside_policy")
    async with get_session(label="payout.request", timeout_seconds=10.0) as session:
        user = (await session.execute(select(User).where(User.telegram_user_id == int(recipient_telegram_user_id)))).scalar_one_or_none()
        if user is None:
            raise PayoutError("user_not_found")
        account = (await session.execute(select(PayoutAccountRecord).where(
            PayoutAccountRecord.user_id == int(user.id), PayoutAccountRecord.currency == "NGN", PayoutAccountRecord.verified.is_(True),
        ))).scalar_one_or_none()
        if account is None:
            raise PayoutError("verified_payout_account_required")
        entropy = f"{user.id}|{account.id}|{amount_kobo}|{now_utc_naive().isoformat()}"
        reference = "srp_" + hashlib.sha256(entropy.encode()).hexdigest()[:28]
        row = PayoutRequestRecord(
            reference=reference, user_id=int(user.id), payout_account_id=int(account.id),
            amount_kobo=amount_kobo, currency="NGN", status="requested", reason=str(reason or "Payout")[:256],
            meta={
                "source": "owner_admin_disbursement",
                "paper_pnl_is_cash": False,
                "requested_by_telegram_id": int(requested_by_telegram_id),
                "recipient_telegram_user_id": int(recipient_telegram_user_id),
            },
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def approve_and_submit_payout(*, reference: str, approver_telegram_id: int) -> PayoutSubmission:
    report = evaluate_financial_activation()
    if not report.ok or not report.payouts_requested:
        raise PayoutError("real_payout_activation_not_ready")
    from core.settings import OWNER_IDS, ADMIN_IDS
    if int(approver_telegram_id) not in set(OWNER_IDS) | set(ADMIN_IDS):
        raise PayoutError("owner_or_admin_approval_required")

    async with get_session(label="payout.approve", timeout_seconds=10.0) as session:
        row = (await session.execute(select(PayoutRequestRecord).where(PayoutRequestRecord.reference == str(reference)).with_for_update())).scalar_one_or_none()
        if row is None:
            raise PayoutError("payout_request_not_found")
        if row.status not in {"requested", "approved", "submitting"}:
            if row.status in {"submitted", "success"}:
                return PayoutSubmission(row.reference, row.status, row.provider_transfer_code)
            raise PayoutError("payout_not_approvable")
        account = await session.get(PayoutAccountRecord, row.payout_account_id)
        if account is None or not account.verified:
            raise PayoutError("verified_payout_account_required")
        recipient_code = decrypt_secret(str(account.recipient_code_encrypted or ""))
        if not recipient_code:
            raise PayoutError("recipient_code_unavailable")
        row.status = "submitting"
        row.approved_by_telegram_id = int(approver_telegram_id)
        row.approved_at = now_utc_naive()
        await session.commit()
        amount_kobo = int(row.amount_kobo)
        reason = str(row.reason or "SignalRankAI payout")

    data = await _paystack("POST", "/transfer", body={
        "source": "balance", "amount": amount_kobo, "recipient": recipient_code,
        "reference": str(reference), "reason": reason, "currency": "NGN",
    })
    transfer_code = str(data.get("transfer_code") or "").strip() or None
    status = str(data.get("status") or "pending").lower()
    async with get_session(label="payout.submitted", timeout_seconds=10.0) as session:
        row = (await session.execute(select(PayoutRequestRecord).where(PayoutRequestRecord.reference == str(reference)).with_for_update())).scalar_one()
        row.status = "submitted" if status in {"pending", "otp", "success"} else "failed"
        row.provider_transfer_code = transfer_code
        row.submitted_at = now_utc_naive()
        row.meta = {**dict(row.meta or {}), "provider_status": status}
        await session.commit()
        final_status = row.status
    return PayoutSubmission(str(reference), final_status, transfer_code)


async def finalize_payout(*, reference: str, otp: str, approver_telegram_id: int) -> PayoutSubmission:
    """Finalize an OTP-gated Paystack transfer; owner/admin only."""
    report = evaluate_financial_activation()
    if not report.ok or not report.payouts_requested:
        raise PayoutError("real_payout_activation_not_ready")
    from core.settings import OWNER_IDS, ADMIN_IDS
    if int(approver_telegram_id) not in set(OWNER_IDS) | set(ADMIN_IDS):
        raise PayoutError("owner_or_admin_approval_required")
    otp_text = re.sub(r"\D", "", str(otp or ""))
    if len(otp_text) < 4 or len(otp_text) > 10:
        raise PayoutError("invalid_transfer_otp")
    async with get_session(label="payout.finalize.read", timeout_seconds=10.0) as session:
        row = (await session.execute(select(PayoutRequestRecord).where(PayoutRequestRecord.reference == str(reference)).with_for_update())).scalar_one_or_none()
        if row is None or not row.provider_transfer_code:
            raise PayoutError("payout_transfer_not_ready_for_otp")
        if row.status in {"success", "reversed", "failed"}:
            return PayoutSubmission(row.reference, row.status, row.provider_transfer_code)
        transfer_code = str(row.provider_transfer_code)
    data = await _paystack("POST", "/transfer/finalize_transfer", body={"transfer_code": transfer_code, "otp": otp_text})
    provider_status = str(data.get("status") or "pending").lower()
    async with get_session(label="payout.finalize.write", timeout_seconds=10.0) as session:
        row = (await session.execute(select(PayoutRequestRecord).where(PayoutRequestRecord.reference == str(reference)).with_for_update())).scalar_one()
        row.status = "submitted" if provider_status in {"pending", "success"} else "failed"
        row.meta = {**dict(row.meta or {}), "provider_status": provider_status, "otp_finalized": True}
        row.submitted_at = row.submitted_at or now_utc_naive()
        await session.commit()
        status = row.status
    return PayoutSubmission(str(reference), status, transfer_code)


async def apply_transfer_event(event: str, data: dict[str, Any]) -> bool:
    reference = str(data.get("reference") or "").strip()
    if not reference or event not in {"transfer.success", "transfer.failed", "transfer.reversed"}:
        return False
    status_map = {"transfer.success": "success", "transfer.failed": "failed", "transfer.reversed": "reversed"}
    async with get_session(label="payout.webhook", timeout_seconds=10.0) as session:
        row = (await session.execute(select(PayoutRequestRecord).where(PayoutRequestRecord.reference == reference).with_for_update())).scalar_one_or_none()
        if row is None:
            return False
        row.status = status_map[event]
        row.provider_transfer_code = str(data.get("transfer_code") or row.provider_transfer_code or "") or None
        row.completed_at = now_utc_naive()
        row.failure_code = str(data.get("gateway_response") or data.get("failures") or "")[:128] or None
        row.meta = {**dict(row.meta or {}), "webhook_event": event}
        await session.commit()
    return True


async def verify_transfer(reference: str) -> dict[str, Any]:
    ref = str(reference or "").strip()
    if not ref:
        raise PayoutError("payout_reference_required")
    data = await _paystack("GET", f"/transfer/verify/{ref}")
    provider_status = str(data.get("status") or "pending").strip().lower()
    status_map = {
        "success": "success",
        "successful": "success",
        "failed": "failed",
        "reversed": "reversed",
        "pending": "submitted",
        "otp": "submitted",
        "processing": "submitted",
    }
    local_status = status_map.get(provider_status, "submitted")
    async with get_session(label="payout.verify", timeout_seconds=10.0) as session:
        row = (await session.execute(
            select(PayoutRequestRecord)
            .where(PayoutRequestRecord.reference == ref)
            .with_for_update()
        )).scalar_one_or_none()
        if row is None:
            raise PayoutError("payout_request_not_found")
        row.status = local_status
        row.provider_transfer_code = str(data.get("transfer_code") or row.provider_transfer_code or "") or None
        row.failure_code = (
            str(data.get("gateway_response") or data.get("reason") or "")[:128] or None
            if local_status in {"failed", "reversed"}
            else None
        )
        if local_status in {"success", "failed", "reversed"}:
            row.completed_at = row.completed_at or now_utc_naive()
        row.meta = {**dict(row.meta or {}), "verified_provider_status": provider_status}
        await session.commit()
    return {**data, "local_status": local_status}


__all__ = [
    "PayoutError", "PayoutSubmission", "apply_transfer_event", "approve_and_submit_payout",
    "create_payout_request", "finalize_payout", "verify_and_store_payout_account", "verify_transfer",
]
