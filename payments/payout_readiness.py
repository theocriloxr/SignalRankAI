"""Manual-approval payout readiness boundary for Nigerian operations."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class PayoutStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    SUBMITTED = "submitted"
    PAID = "paid"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class PayoutAccount:
    owner_id: int
    bank_name: str
    account_last4: str
    recipient_code: str | None = None
    verified: bool = False

    @property
    def masked_account(self) -> str:
        return f"****{str(self.account_last4)[-4:]}"


@dataclass(frozen=True, slots=True)
class PayoutRequest:
    payout_id: str
    owner_id: int
    amount: float
    currency: str = "NGN"
    status: PayoutStatus = PayoutStatus.REQUESTED
    requested_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    approved_by: int | None = None


def create_payout_request(*, owner_id: int, amount: float, account: PayoutAccount) -> PayoutRequest:
    if int(owner_id) != int(account.owner_id):
        raise PermissionError("payout_account_owner_mismatch")
    if not account.verified:
        raise ValueError("payout_account_not_verified")
    if float(amount) <= 0:
        raise ValueError("payout_amount_must_be_positive")
    digest = hashlib.sha256(f"{owner_id}|{amount}|{account.masked_account}".encode()).hexdigest()[:20]
    return PayoutRequest(f"PO-{digest}", int(owner_id), float(amount))


def approve_payout(request: PayoutRequest, *, approver_id: int, owner_id: int) -> PayoutRequest:
    if int(approver_id) != int(owner_id):
        raise PermissionError("owner_approval_required")
    if request.status is not PayoutStatus.REQUESTED:
        raise ValueError("payout_not_pending")
    return PayoutRequest(request.payout_id, request.owner_id, request.amount, request.currency, PayoutStatus.APPROVED, request.requested_at, int(approver_id))


def payout_readiness_status() -> dict[str, Any]:
    return {"real_payouts_enabled": False, "manual_approval_required": True, "trading_capital_separated": True, "paper_pnl_is_not_cash": True}


__all__ = ["PayoutAccount", "PayoutRequest", "PayoutStatus", "approve_payout", "create_payout_request", "payout_readiness_status"]
