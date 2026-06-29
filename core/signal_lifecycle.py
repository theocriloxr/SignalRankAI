"""Canonical signal lifecycle states used by generation, delivery, and outcomes."""

from __future__ import annotations

from enum import StrEnum


class SignalLifecycle(StrEnum):
    NEW = "new"
    ACTIVE = "active"
    ENTRY_HIT = "entry_hit"
    TP1 = "tp1"
    TP2 = "tp2"
    TP3 = "tp3"
    SL = "sl"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


TERMINAL_SIGNAL_STATES = {
    SignalLifecycle.TP3.value,
    SignalLifecycle.SL.value,
    SignalLifecycle.EXPIRED.value,
    SignalLifecycle.CANCELLED.value,
    SignalLifecycle.ARCHIVED.value,
}


def lifecycle_state_for_outcome(status: str | None) -> str:
    """Map an outcome status to the canonical signal lifecycle state."""
    status_l = str(status or "").strip().lower()
    if status_l in {"tp", "tp3"}:
        return SignalLifecycle.TP3.value
    if status_l == "tp2":
        return SignalLifecycle.TP2.value
    if status_l == "tp1":
        return SignalLifecycle.TP1.value
    if status_l == "sl":
        return SignalLifecycle.SL.value
    if status_l in {"time_stop", "expired", "missed"}:
        return SignalLifecycle.EXPIRED.value
    if status_l in {"invalid", "invalidated", "cancel", "cancelled"}:
        return SignalLifecycle.CANCELLED.value
    return SignalLifecycle.ACTIVE.value
