"""Canonical delivery-proof state interpretation shared by all consumers."""

from __future__ import annotations

from typing import Any


CONFIRMED_DELIVERY_STATES = frozenset({"sent", "confirmed", "delivered", "reconciled"})


def normalize_delivery_state(value: Any) -> str:
    return str(value or "").strip().lower()


def is_confirmed_delivery_state(value: Any) -> bool:
    return normalize_delivery_state(value) in CONFIRMED_DELIVERY_STATES


def has_durable_delivery_proof(delivery: Any) -> bool:
    """Return true only for a successful, addressable Telegram delivery."""
    return bool(
        getattr(delivery, "sent_ok", False)
        and is_confirmed_delivery_state(getattr(delivery, "delivery_state", None))
        and getattr(delivery, "telegram_chat_id", None) is not None
        and getattr(delivery, "telegram_message_id", None) is not None
        and getattr(delivery, "delivery_confirmed_at", None) is not None
    )


__all__ = [
    "CONFIRMED_DELIVERY_STATES",
    "has_durable_delivery_proof",
    "is_confirmed_delivery_state",
    "normalize_delivery_state",
]
