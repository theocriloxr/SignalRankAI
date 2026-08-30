"""Pure delivery identity, state-machine, and ambiguity policy.

The existing ``signal_deliveries`` row is the durable reservation/outbox.  This
module keeps the transition rules independent from Telegram and SQLAlchemy so
every legacy delivery entry point can use the same contract while the larger
runtime decomposition remains deferred to its planned phase.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class DeliveryState(StrEnum):
    RESERVED = "RESERVED"
    VALIDATING = "VALIDATING"
    SENDING = "SENDING"
    SENT = "SENT"
    PROOF_PENDING = "PROOF_PENDING"
    CONFIRMED = "CONFIRMED"
    BLOCKED = "BLOCKED"
    FAILED_PRE_SEND = "FAILED_PRE_SEND"
    AMBIGUOUS = "AMBIGUOUS"
    RECONCILED = "RECONCILED"


_ALIASES: dict[str, DeliveryState] = {
    "PENDING": DeliveryState.RESERVED,
    "RESERVED": DeliveryState.RESERVED,
    "VALIDATING": DeliveryState.VALIDATING,
    "SENDING": DeliveryState.SENDING,
    "SENT": DeliveryState.SENT,
    "UPDATED": DeliveryState.SENT,
    "DIGEST": DeliveryState.SENT,
    "PROOF_PENDING": DeliveryState.PROOF_PENDING,
    "CONFIRMED": DeliveryState.CONFIRMED,
    "DELIVERED": DeliveryState.CONFIRMED,
    "RECONCILED": DeliveryState.RECONCILED,
    "BLOCKED": DeliveryState.BLOCKED,
    "SKIPPED": DeliveryState.BLOCKED,
    "FORMATTER_FAILED": DeliveryState.BLOCKED,
    "FAILED": DeliveryState.FAILED_PRE_SEND,
    "FAILED_PRE_SEND": DeliveryState.FAILED_PRE_SEND,
    "AMBIGUOUS": DeliveryState.AMBIGUOUS,
}

SUCCESS_STATES = frozenset({DeliveryState.CONFIRMED, DeliveryState.RECONCILED})

# Once transmission may have started, automatic reservation retry is unsafe.
# SENDING is intentionally included: a process can die after the Bot API
# accepts a request but before it can record SENT/PROOF_PENDING.
NO_BLIND_RETRY_STATES = frozenset(
    {
        DeliveryState.SENDING,
        DeliveryState.SENT,
        DeliveryState.PROOF_PENDING,
        DeliveryState.CONFIRMED,
        DeliveryState.AMBIGUOUS,
        DeliveryState.RECONCILED,
        DeliveryState.BLOCKED,
    }
)

AMBIGUOUS_ERROR_MARKER = "telegram_delivery_ambiguous"


@dataclass(frozen=True, slots=True)
class DeliveryOperation:
    """Stable, channel-scoped identity for one user-visible delivery."""

    user_id: int
    signal_id: str
    channel_id: int
    signal_version: str = "1"
    delivery_kind: str = "signal"

    def __post_init__(self) -> None:
        signal_id = str(self.signal_id or "").strip()
        if not signal_id:
            raise ValueError("signal_id is required for a delivery operation")
        object.__setattr__(self, "user_id", int(self.user_id))
        object.__setattr__(self, "channel_id", int(self.channel_id))
        object.__setattr__(self, "signal_id", signal_id)
        object.__setattr__(self, "signal_version", str(self.signal_version or "1").strip() or "1")
        object.__setattr__(self, "delivery_kind", str(self.delivery_kind or "signal").strip() or "signal")

    @property
    def idempotency_key(self) -> str:
        raw = "|".join(
            (
                str(self.user_id),
                self.signal_id,
                str(self.channel_id),
                self.signal_version,
                self.delivery_kind,
            )
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "signal_id": self.signal_id,
            "channel_id": self.channel_id,
            "signal_version": self.signal_version,
            "delivery_kind": self.delivery_kind,
            "idempotency_key": self.idempotency_key,
        }


class TelegramDeliveryAmbiguous(RuntimeError):
    """The request may have reached Telegram, so retrying could duplicate it."""

    def __init__(self, detail: str = "Telegram send timed out after transmission began") -> None:
        super().__init__(f"{AMBIGUOUS_ERROR_MARKER}: {detail}")


def is_ambiguous_send_error(error: BaseException) -> bool:
    if isinstance(error, TelegramDeliveryAmbiguous):
        return True
    if isinstance(error, (asyncio.TimeoutError, TimeoutError)):
        return True
    # PTB/httpx timeout and connection failures do not prove non-delivery.
    name = type(error).__name__.strip().lower()
    return name in {
        "timedout",
        "readtimeout",
        "writetimeout",
        "connecttimeout",
        "pooltimeout",
        "networkerror",
    }


def canonical_delivery_state(
    value: DeliveryState | str | None,
    *,
    sent_ok: bool = False,
    proof_ok: bool = False,
    error: str | None = None,
) -> DeliveryState:
    error_l = str(error or "").strip().lower()
    if AMBIGUOUS_ERROR_MARKER in error_l:
        return DeliveryState.AMBIGUOUS
    raw = str(value or "").strip().upper()
    requested = _ALIASES.get(raw)
    if sent_ok and proof_ok:
        return DeliveryState.RECONCILED if requested is DeliveryState.RECONCILED else DeliveryState.CONFIRMED
    if requested is not None:
        return requested
    return DeliveryState.FAILED_PRE_SEND if error_l else DeliveryState.RESERVED


def is_success_state(value: DeliveryState | str | None) -> bool:
    return canonical_delivery_state(value) in SUCCESS_STATES


def forbids_blind_retry(value: DeliveryState | str | None) -> bool:
    return canonical_delivery_state(value) in NO_BLIND_RETRY_STATES


def transition_allowed(
    current: DeliveryState | str | None,
    target: DeliveryState | str,
    *,
    proof_ok: bool = False,
) -> bool:
    """Return whether a durable row may move to ``target``.

    Telegram proof may resolve any non-success state.  A confirmed/reconciled
    operation is monotonic and an ambiguous operation can only be resolved by
    a recovered receipt.
    """

    current_state = canonical_delivery_state(current)
    target_state = canonical_delivery_state(target, sent_ok=proof_ok, proof_ok=proof_ok)
    if current_state in SUCCESS_STATES:
        return target_state in SUCCESS_STATES
    if target_state in SUCCESS_STATES:
        return bool(proof_ok)
    if current_state is DeliveryState.AMBIGUOUS:
        return False
    if current_state is DeliveryState.BLOCKED:
        return target_state is DeliveryState.BLOCKED
    if current_state in {DeliveryState.SENT, DeliveryState.PROOF_PENDING}:
        return target_state in {DeliveryState.SENT, DeliveryState.PROOF_PENDING}

    rank = {
        DeliveryState.RESERVED: 0,
        DeliveryState.VALIDATING: 1,
        DeliveryState.SENDING: 2,
        DeliveryState.SENT: 3,
        DeliveryState.PROOF_PENDING: 4,
    }
    if current_state in rank and target_state in rank:
        return rank[target_state] >= rank[current_state]
    return True
