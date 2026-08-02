"""Monotonic ordering policy for user-facing outcome notifications."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_STAGE_RANKS = {
    "pending": 0,
    "entry": 1,
    "entered": 1,
    "tp1": 10,
    "partial_win": 15,
    "tp2": 20,
    "partial_win_be": 25,
    "breakeven": 25,
    "be": 25,
    "tp3": 30,
    "sl": 30,
    "stop": 30,
    "stopped": 30,
    "missed": 30,
    "expired": 30,
    "cancelled": 30,
    "closed": 30,
}
_TERMINAL = {"tp3", "sl", "stop", "stopped", "missed", "expired", "cancelled", "closed"}


def canonical_outcome_status(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")[:16]


def outcome_stage_rank(value: Any) -> int:
    return int(_STAGE_RANKS.get(canonical_outcome_status(value), 0))


def outcome_is_terminal(value: Any) -> bool:
    return canonical_outcome_status(value) in _TERMINAL


@dataclass(frozen=True, slots=True)
class OutcomeDeliveryDecision:
    allowed: bool
    reason: str
    candidate_rank: int


def evaluate_outcome_delivery(
    candidate_status: Any,
    *,
    highest_delivered_rank: int = 0,
    terminal_already_delivered: bool = False,
) -> OutcomeDeliveryDecision:
    status = canonical_outcome_status(candidate_status)
    rank = outcome_stage_rank(status)
    if terminal_already_delivered:
        return OutcomeDeliveryDecision(False, "terminal_already_delivered", rank)
    if rank < int(highest_delivered_rank or 0):
        return OutcomeDeliveryDecision(False, "lower_stage_already_surpassed", rank)
    if rank == int(highest_delivered_rank or 0) and rank > 0:
        return OutcomeDeliveryDecision(False, "stage_already_delivered", rank)
    return OutcomeDeliveryDecision(True, "monotonic", rank)
