"""Canonical delivery-provenance rules for live outcome tracking.

Live performance is permitted only for signals that have an acknowledged
Telegram delivery. Paper, shadow, backtest and legacy records remain separate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


LIVE_DELIVERED = "LIVE_DELIVERED"
PAPER = "PAPER"
SHADOW = "SHADOW"
BACKTEST = "BACKTEST"
WALK_FORWARD = "WALK_FORWARD"
LEGACY_UNVERIFIED = "LEGACY_UNVERIFIED"
INVALIDATED_UNDELIVERED = "INVALIDATED_UNDELIVERED"

_VALID_LIVE_STATES = {
    "DELIVERED",
    "WATCHING_ENTRY",
    "WATCHING_FOR_ENTRY",
    "ENTRY_TOUCHED",
    "ACTIVE",
    "ACTIVE_TRADE",
    "TP1",
    "TP1_HIT",
    "TP2",
    "TP2_HIT",
    "TP3",
    "TP3_HIT",
    "SL",
    "SL_HIT",
    "EXPIRED",
    "MISSED_ENTRY",
    "BREAKEVEN_STOP",
}


@dataclass(frozen=True, slots=True)
class OutcomeEligibility:
    eligible: bool
    category: str
    reason: str
    delivery_id: int | str | None = None


def _value(record: Any, name: str, default: Any = None) -> Any:
    if record is None:
        return default
    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)


def evaluate_outcome_eligibility(
    signal: Any,
    delivery: Any = None,
    lifecycle: Any = None,
) -> OutcomeEligibility:
    """Return the authoritative outcome category and eligibility decision."""
    meta = _value(signal, "meta", {}) or {}
    source = str(
        _value(signal, "outcome_category", None)
        or _value(signal, "source", None)
        or (meta.get("outcome_category") if isinstance(meta, Mapping) else None)
        or (meta.get("source") if isinstance(meta, Mapping) else None)
        or ""
    ).upper().strip()

    if bool(_value(signal, "is_shadow", False)) or source == SHADOW:
        return OutcomeEligibility(False, SHADOW, "shadow_signal")
    if bool(_value(signal, "is_paper", False)) or source == PAPER:
        return OutcomeEligibility(False, PAPER, "paper_signal")
    if bool(_value(signal, "is_backtest", False)) or source == BACKTEST:
        return OutcomeEligibility(False, BACKTEST, "backtest_signal")
    if source in {WALK_FORWARD, "WFO"}:
        return OutcomeEligibility(False, WALK_FORWARD, "walk_forward_signal")

    delivery_id = _value(delivery, "id", None)
    sent_ok = bool(_value(delivery, "sent_ok", False))
    chat_id = _value(delivery, "telegram_chat_id", None)
    message_id = _value(delivery, "telegram_message_id", None)
    confirmed_at = _value(delivery, "delivery_confirmed_at", None)
    delivery_state = str(_value(delivery, "delivery_state", "") or "").upper().strip()
    proof_ok = bool(sent_ok and chat_id is not None and message_id is not None)

    if not proof_ok:
        return OutcomeEligibility(
            False,
            LEGACY_UNVERIFIED if delivery is None else INVALIDATED_UNDELIVERED,
            "missing_verified_delivery_proof",
            delivery_id,
        )
    if delivery_state not in {"CONFIRMED", "DELIVERED", "RECONCILED"}:
        return OutcomeEligibility(False, INVALIDATED_UNDELIVERED, "delivery_not_confirmed", delivery_id)
    if confirmed_at is None:
        return OutcomeEligibility(False, INVALIDATED_UNDELIVERED, "missing_delivery_timestamp", delivery_id)

    lifecycle_state = str(
        _value(lifecycle, "state", None)
        or _value(signal, "lifecycle_state", None)
        or "WATCHING_FOR_ENTRY"
    ).upper().strip()
    if lifecycle_state not in _VALID_LIVE_STATES:
        return OutcomeEligibility(False, INVALIDATED_UNDELIVERED, f"invalid_lifecycle_state:{lifecycle_state}", delivery_id)

    return OutcomeEligibility(True, LIVE_DELIVERED, "verified_delivery", delivery_id)


__all__ = [
    "OutcomeEligibility",
    "evaluate_outcome_eligibility",
    "LIVE_DELIVERED",
    "PAPER",
    "SHADOW",
    "BACKTEST",
    "WALK_FORWARD",
    "LEGACY_UNVERIFIED",
    "INVALIDATED_UNDELIVERED",
]
