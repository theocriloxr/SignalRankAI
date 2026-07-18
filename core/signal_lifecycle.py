"""Canonical, monotonic signal lifecycle contract.

This module is deliberately pure. Outcome workers, database repositories, and
interactive snapshot readers all normalize legacy values through this graph so
there is one definition of progression and terminality.
"""

from __future__ import annotations

from enum import StrEnum


class SignalLifecycle(StrEnum):
    WATCHING_FOR_ENTRY = "WATCHING_FOR_ENTRY"
    ACTIVE_TRADE = "ACTIVE_TRADE"
    TP1_HIT = "TP1_HIT"
    TP2_HIT = "TP2_HIT"
    TP3_HIT = "TP3_HIT"
    SL_HIT = "SL_HIT"
    BREAKEVEN_STOP = "BREAKEVEN_STOP"
    MISSED_ENTRY = "MISSED_ENTRY"
    EXPIRED = "EXPIRED"


WATCHING_FOR_ENTRY = SignalLifecycle.WATCHING_FOR_ENTRY.value
ACTIVE_TRADE = SignalLifecycle.ACTIVE_TRADE.value
TP1_HIT = SignalLifecycle.TP1_HIT.value
TP2_HIT = SignalLifecycle.TP2_HIT.value
TP3_HIT = SignalLifecycle.TP3_HIT.value
SL_HIT = SignalLifecycle.SL_HIT.value
BREAKEVEN_STOP = SignalLifecycle.BREAKEVEN_STOP.value
MISSED_ENTRY = SignalLifecycle.MISSED_ENTRY.value
EXPIRED = SignalLifecycle.EXPIRED.value

TERMINAL_SIGNAL_STATES = frozenset(
    {TP3_HIT, SL_HIT, BREAKEVEN_STOP, MISSED_ENTRY, EXPIRED}
)

_LEGACY_ALIASES = {
    "": WATCHING_FOR_ENTRY,
    "NEW": WATCHING_FOR_ENTRY,
    "WATCHING": WATCHING_FOR_ENTRY,
    "WATCHING_FOR_ENTRY": WATCHING_FOR_ENTRY,
    "ACTIVE": ACTIVE_TRADE,
    "ENTRY_HIT": ACTIVE_TRADE,
    "ACTIVE_TRADE": ACTIVE_TRADE,
    "TP1": TP1_HIT,
    "TP1_HIT": TP1_HIT,
    "TP2": TP2_HIT,
    "TP2_HIT": TP2_HIT,
    "TP": TP3_HIT,
    "TP3": TP3_HIT,
    "TP3_HIT": TP3_HIT,
    "SL": SL_HIT,
    "SL_HIT": SL_HIT,
    "BREAKEVEN": BREAKEVEN_STOP,
    "BREAKEVEN_STOP": BREAKEVEN_STOP,
    "PARTIAL_WIN_BE": BREAKEVEN_STOP,
    "MISSED": MISSED_ENTRY,
    "MISSED_ENTRY": MISSED_ENTRY,
    "TIME_STOP": EXPIRED,
    "CANCELLED": EXPIRED,
    "CANCELED": EXPIRED,
    "ARCHIVED": EXPIRED,
    "EXPIRED": EXPIRED,
}

EVENT_TO_STATE = {
    "generated": WATCHING_FOR_ENTRY,
    "entry_touched": ACTIVE_TRADE,
    "halfway_to_tp1": ACTIVE_TRADE,
    "breakeven_moved": ACTIVE_TRADE,
    "tp1_hit": TP1_HIT,
    "tp2_hit": TP2_HIT,
    "tp3_hit": TP3_HIT,
    "sl_hit": SL_HIT,
    "breakeven_stop": BREAKEVEN_STOP,
    "missed_entry": MISSED_ENTRY,
    "expired": EXPIRED,
}

_ALLOWED_TARGETS = {
    WATCHING_FOR_ENTRY: frozenset({WATCHING_FOR_ENTRY, ACTIVE_TRADE, MISSED_ENTRY, EXPIRED}),
    ACTIVE_TRADE: frozenset({ACTIVE_TRADE, TP1_HIT, TP2_HIT, TP3_HIT, SL_HIT, EXPIRED}),
    TP1_HIT: frozenset({TP1_HIT, TP2_HIT, TP3_HIT, BREAKEVEN_STOP, EXPIRED}),
    TP2_HIT: frozenset({TP2_HIT, TP3_HIT, BREAKEVEN_STOP, EXPIRED}),
    TP3_HIT: frozenset({TP3_HIT}),
    SL_HIT: frozenset({SL_HIT}),
    BREAKEVEN_STOP: frozenset({BREAKEVEN_STOP}),
    MISSED_ENTRY: frozenset({MISSED_ENTRY}),
    EXPIRED: frozenset({EXPIRED}),
}


def normalize_lifecycle_state(value: SignalLifecycle | str | None) -> str:
    raw = str(value or "").strip().upper()
    return _LEGACY_ALIASES.get(raw, WATCHING_FOR_ENTRY)


def lifecycle_state_for_event(event_type: str | None) -> str:
    return EVENT_TO_STATE.get(str(event_type or "").strip().lower(), WATCHING_FOR_ENTRY)


def lifecycle_transition_allowed(
    current: SignalLifecycle | str | None,
    target: SignalLifecycle | str | None,
) -> bool:
    current_state = normalize_lifecycle_state(current)
    target_state = normalize_lifecycle_state(target)
    return target_state in _ALLOWED_TARGETS[current_state]


def event_transition_allowed(current: SignalLifecycle | str | None, event_type: str) -> bool:
    return lifecycle_transition_allowed(current, lifecycle_state_for_event(event_type))


def highest_tp_for_state(value: SignalLifecycle | str | None) -> int:
    state = normalize_lifecycle_state(value)
    return {TP1_HIT: 1, TP2_HIT: 2, TP3_HIT: 3}.get(state, 0)


def lifecycle_state_for_outcome(status: str | None) -> str:
    """Map an outcome status to the canonical uppercase lifecycle state."""
    status_l = str(status or "").strip().lower()
    if status_l in {"tp", "tp3"}:
        return TP3_HIT
    if status_l == "tp2":
        return TP2_HIT
    if status_l == "tp1":
        return TP1_HIT
    if status_l == "sl":
        return SL_HIT
    if status_l == "partial_win_be":
        return BREAKEVEN_STOP
    if status_l in {"missed", "missed_entry"}:
        return MISSED_ENTRY
    if status_l in {"time_stop", "expired", "invalid", "invalidated", "cancel", "cancelled"}:
        return EXPIRED
    return ACTIVE_TRADE


_OUTCOME_PROGRESS = {
    "": 0,
    "pending": 0,
    "tp1": 1,
    "tp2": 2,
    "tp3": 3,
    "tp": 3,
}
_TERMINAL_OUTCOMES = frozenset(
    {"tp", "tp3", "sl", "partial_win_be", "time_stop", "missed_entry", "expired", "invalid", "invalidated"}
)


def outcome_transition_allowed(current: str | None, target: str | None) -> bool:
    """Prevent outcome replay/reordering from downgrading authoritative truth."""
    current_l = str(current or "").strip().lower()
    target_l = str(target or "").strip().lower()
    if not target_l:
        return False
    if current_l == target_l:
        return True
    if current_l in _TERMINAL_OUTCOMES:
        return False
    if target_l in _TERMINAL_OUTCOMES:
        return True
    return _OUTCOME_PROGRESS.get(target_l, 0) >= _OUTCOME_PROGRESS.get(current_l, 0)


__all__ = [
    "ACTIVE_TRADE",
    "BREAKEVEN_STOP",
    "EXPIRED",
    "MISSED_ENTRY",
    "SignalLifecycle",
    "SL_HIT",
    "TERMINAL_SIGNAL_STATES",
    "TP1_HIT",
    "TP2_HIT",
    "TP3_HIT",
    "WATCHING_FOR_ENTRY",
    "event_transition_allowed",
    "highest_tp_for_state",
    "lifecycle_state_for_event",
    "lifecycle_state_for_outcome",
    "lifecycle_transition_allowed",
    "normalize_lifecycle_state",
    "outcome_transition_allowed",
]
