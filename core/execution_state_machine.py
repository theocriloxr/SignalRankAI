"""Canonical execution/order and position lifecycle for broker adapters.

Provider adapters may observe events out of order.  Persistence is therefore
governed by one monotonic transition graph rather than ad-hoc string writes.
Terminal execution states are absorbing; same-state observations are idempotent.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping


class ExecutionState(str, Enum):
    RESERVED = "reserved"
    SUBMITTING = "submitting"
    AMBIGUOUS = "ambiguous"
    CONFIRMED = "confirmed"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    OPEN = "open"
    RECONCILIATION_PENDING = "reconciliation_pending"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"
    BLOCKED = "blocked"


class PositionState(str, Enum):
    NONE = "none"
    PENDING_ENTRY = "pending_entry"
    OPEN = "open"
    RECONCILING = "reconciling"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    FAILED = "failed"


_ALIASES = {
    "pending": ExecutionState.RESERVED,
    "new": ExecutionState.CONFIRMED,
    "submitted": ExecutionState.CONFIRMED,
    "success": ExecutionState.CONFIRMED,
    "partiallyfilled": ExecutionState.PARTIALLY_FILLED,
    "partially_filled": ExecutionState.PARTIALLY_FILLED,
    "deactivated": ExecutionState.CANCELLED,
    "canceled": ExecutionState.CANCELLED,
}

_TERMINAL = frozenset(
    {
        ExecutionState.CLOSED,
        ExecutionState.CANCELLED,
        ExecutionState.REJECTED,
        ExecutionState.FAILED,
        ExecutionState.BLOCKED,
    }
)

_TRANSITIONS: dict[ExecutionState, frozenset[ExecutionState]] = {
    ExecutionState.RESERVED: frozenset(
        {
            ExecutionState.SUBMITTING,
            ExecutionState.CONFIRMED,
            ExecutionState.OPEN,  # provider acknowledgement may already be a position
            ExecutionState.BLOCKED,
            ExecutionState.CANCELLED,
            ExecutionState.REJECTED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.SUBMITTING: frozenset(
        {
            ExecutionState.AMBIGUOUS,
            ExecutionState.CONFIRMED,
            ExecutionState.OPEN,
            ExecutionState.RECONCILIATION_PENDING,
            ExecutionState.CANCELLED,
            ExecutionState.REJECTED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.AMBIGUOUS: frozenset(
        {
            ExecutionState.CONFIRMED,
            ExecutionState.PARTIALLY_FILLED,
            ExecutionState.FILLED,
            ExecutionState.OPEN,
            ExecutionState.RECONCILIATION_PENDING,
            ExecutionState.CANCELLED,
            ExecutionState.REJECTED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.CONFIRMED: frozenset(
        {
            ExecutionState.PARTIALLY_FILLED,
            ExecutionState.FILLED,
            ExecutionState.OPEN,
            ExecutionState.RECONCILIATION_PENDING,
            ExecutionState.CANCELLED,
            ExecutionState.REJECTED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.PARTIALLY_FILLED: frozenset(
        {
            ExecutionState.FILLED,
            ExecutionState.OPEN,
            ExecutionState.RECONCILIATION_PENDING,
            ExecutionState.CLOSED,
            ExecutionState.CANCELLED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.FILLED: frozenset(
        {
            ExecutionState.OPEN,
            ExecutionState.RECONCILIATION_PENDING,
            ExecutionState.CLOSED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.OPEN: frozenset(
        {
            ExecutionState.RECONCILIATION_PENDING,
            ExecutionState.CLOSED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.RECONCILIATION_PENDING: frozenset(
        {
            ExecutionState.CONFIRMED,
            ExecutionState.PARTIALLY_FILLED,
            ExecutionState.FILLED,
            ExecutionState.OPEN,
            ExecutionState.CLOSED,
            ExecutionState.CANCELLED,
            ExecutionState.REJECTED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.CLOSED: frozenset(),
    ExecutionState.CANCELLED: frozenset(),
    ExecutionState.REJECTED: frozenset(),
    ExecutionState.FAILED: frozenset(),
    ExecutionState.BLOCKED: frozenset(),
}


class InvalidExecutionTransition(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExecutionTransition:
    current: ExecutionState
    target: ExecutionState
    idempotent: bool
    position_state: PositionState


def normalize_execution_state(value: ExecutionState | str | None) -> ExecutionState:
    raw = str(value.value if isinstance(value, ExecutionState) else value or "").strip().lower()
    if raw in _ALIASES:
        return _ALIASES[raw]
    try:
        return ExecutionState(raw)
    except ValueError as exc:
        raise InvalidExecutionTransition(f"unknown_execution_state:{raw or 'missing'}") from exc


def is_terminal_execution_state(value: ExecutionState | str | None) -> bool:
    return normalize_execution_state(value) in _TERMINAL


def position_state_for_execution(value: ExecutionState | str | None) -> PositionState:
    state = normalize_execution_state(value)
    if state in {ExecutionState.RESERVED, ExecutionState.SUBMITTING, ExecutionState.CONFIRMED}:
        return PositionState.PENDING_ENTRY
    if state == ExecutionState.AMBIGUOUS or state == ExecutionState.RECONCILIATION_PENDING:
        return PositionState.RECONCILING
    if state in {ExecutionState.PARTIALLY_FILLED, ExecutionState.FILLED, ExecutionState.OPEN}:
        return PositionState.OPEN
    if state == ExecutionState.CLOSED:
        return PositionState.CLOSED
    if state == ExecutionState.CANCELLED:
        return PositionState.CANCELLED
    if state in {ExecutionState.REJECTED, ExecutionState.FAILED, ExecutionState.BLOCKED}:
        return PositionState.FAILED
    return PositionState.NONE


def evaluate_execution_transition(
    current: ExecutionState | str | None,
    target: ExecutionState | str | None,
) -> ExecutionTransition:
    source = normalize_execution_state(current)
    destination = normalize_execution_state(target)
    if source == destination:
        return ExecutionTransition(
            source,
            destination,
            True,
            position_state_for_execution(destination),
        )
    if destination not in _TRANSITIONS[source]:
        raise InvalidExecutionTransition(
            f"invalid_execution_transition:{source.value}->{destination.value}"
        )
    return ExecutionTransition(
        source,
        destination,
        False,
        position_state_for_execution(destination),
    )


def transition_execution_row(
    row: Any,
    target: ExecutionState | str,
    *,
    now: datetime,
    error_code: str | None = None,
    meta: Mapping[str, Any] | None = None,
    realized_pnl_pct: float | None = None,
    realized_pnl: float | None = None,
    closed_at: datetime | None = None,
) -> ExecutionTransition:
    """Apply one validated transition to a BrokerExecution/MT5Execution-like row."""
    decision = evaluate_execution_transition(getattr(row, "status", None), target)
    row.status = decision.target.value

    if hasattr(row, "updated_at"):
        row.updated_at = now
    if hasattr(row, "error_code"):
        row.error_code = str(error_code or "")[:128] or None
    if meta is not None and hasattr(row, "meta"):
        row.meta = {**dict(getattr(row, "meta", {}) or {}), **dict(meta)}
    if realized_pnl_pct is not None and hasattr(row, "realized_pnl_pct"):
        row.realized_pnl_pct = float(realized_pnl_pct)
    if realized_pnl is not None and hasattr(row, "realized_pnl"):
        row.realized_pnl = float(realized_pnl)

    if decision.target in _TERMINAL and hasattr(row, "closed_at"):
        row.closed_at = closed_at or now
    return decision


__all__ = [
    "ExecutionState",
    "PositionState",
    "ExecutionTransition",
    "InvalidExecutionTransition",
    "normalize_execution_state",
    "is_terminal_execution_state",
    "position_state_for_execution",
    "evaluate_execution_transition",
    "transition_execution_row",
]
