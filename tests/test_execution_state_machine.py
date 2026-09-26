from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.execution_state_machine import (
    ExecutionState,
    InvalidExecutionTransition,
    PositionState,
    evaluate_execution_transition,
    is_terminal_execution_state,
    normalize_execution_state,
    position_state_for_execution,
    transition_execution_row,
)


def test_provider_aliases_normalize_to_canonical_states() -> None:
    assert normalize_execution_state("pending") is ExecutionState.RESERVED
    assert normalize_execution_state("submitted") is ExecutionState.CONFIRMED
    assert normalize_execution_state("New") is ExecutionState.CONFIRMED
    assert normalize_execution_state("PartiallyFilled") is ExecutionState.PARTIALLY_FILLED
    assert normalize_execution_state("deactivated") is ExecutionState.CANCELLED
    assert normalize_execution_state("canceled") is ExecutionState.CANCELLED


def test_standard_execution_path_is_monotonic() -> None:
    path = [
        "reserved",
        "submitting",
        "confirmed",
        "open",
        "reconciliation_pending",
        "closed",
    ]
    for current, target in zip(path, path[1:]):
        decision = evaluate_execution_transition(current, target)
        assert decision.target.value == target
        assert decision.idempotent is False


def test_mt5_provider_ack_can_persist_directly_as_open() -> None:
    decision = evaluate_execution_transition("pending", "open")
    assert decision.current is ExecutionState.RESERVED
    assert decision.target is ExecutionState.OPEN
    assert decision.position_state is PositionState.OPEN


def test_ambiguous_submission_can_only_resolve_forward() -> None:
    for target in (
        "confirmed",
        "partially_filled",
        "filled",
        "open",
        "reconciliation_pending",
        "cancelled",
        "rejected",
        "failed",
    ):
        assert evaluate_execution_transition("ambiguous", target).target.value == target

    with pytest.raises(InvalidExecutionTransition, match="ambiguous->reserved"):
        evaluate_execution_transition("ambiguous", "reserved")


@pytest.mark.parametrize("terminal", ["closed", "cancelled", "rejected", "failed", "blocked"])
def test_terminal_states_are_absorbing_but_idempotent(terminal: str) -> None:
    same = evaluate_execution_transition(terminal, terminal)
    assert same.idempotent is True
    assert is_terminal_execution_state(terminal)

    with pytest.raises(InvalidExecutionTransition):
        evaluate_execution_transition(terminal, "open")


def test_closed_position_cannot_be_reopened_by_stale_provider_event() -> None:
    with pytest.raises(InvalidExecutionTransition, match="closed->open"):
        evaluate_execution_transition("closed", "open")


def test_reconciliation_pending_can_return_open_or_finish_terminal() -> None:
    assert (
        evaluate_execution_transition("reconciliation_pending", "open").target
        is ExecutionState.OPEN
    )
    assert (
        evaluate_execution_transition("reconciliation_pending", "closed").target
        is ExecutionState.CLOSED
    )


@pytest.mark.parametrize(
    ("execution", "position"),
    [
        ("reserved", PositionState.PENDING_ENTRY),
        ("confirmed", PositionState.PENDING_ENTRY),
        ("ambiguous", PositionState.RECONCILING),
        ("reconciliation_pending", PositionState.RECONCILING),
        ("partially_filled", PositionState.OPEN),
        ("filled", PositionState.OPEN),
        ("open", PositionState.OPEN),
        ("closed", PositionState.CLOSED),
        ("cancelled", PositionState.CANCELLED),
        ("rejected", PositionState.FAILED),
        ("failed", PositionState.FAILED),
        ("blocked", PositionState.FAILED),
    ],
)
def test_execution_state_projects_to_one_position_state(
    execution: str,
    position: PositionState,
) -> None:
    assert position_state_for_execution(execution) is position


def test_transition_execution_row_applies_metadata_and_terminal_timestamp() -> None:
    now = datetime(2026, 9, 26, 12, 0, 0)
    row = SimpleNamespace(
        status="open",
        error_code=None,
        updated_at=None,
        closed_at=None,
        realized_pnl_pct=None,
        realized_pnl=None,
        meta={"existing": True},
    )
    decision = transition_execution_row(
        row,
        "closed",
        now=now,
        error_code=None,
        realized_pnl_pct=1.25,
        realized_pnl=12.50,
        meta={"provider_proof": "deal-1"},
    )
    assert decision.target is ExecutionState.CLOSED
    assert row.status == "closed"
    assert row.closed_at == now
    assert row.updated_at == now
    assert row.realized_pnl_pct == 1.25
    assert row.realized_pnl == 12.50
    assert row.meta == {"existing": True, "provider_proof": "deal-1"}


def test_unknown_state_fails_closed() -> None:
    with pytest.raises(InvalidExecutionTransition, match="unknown_execution_state"):
        normalize_execution_state("provider_magic_status")


def test_live_broker_reconcilers_use_canonical_transition_writer() -> None:
    root = Path(__file__).resolve().parents[1]
    bybit_reconciler = (root / "services" / "bybit_reconciler.py").read_text(
        encoding="utf-8"
    )
    mt5_reconciler = (root / "services" / "mt5_reconciler.py").read_text(
        encoding="utf-8"
    )
    bybit_router = (root / "services" / "bybit_signal_router.py").read_text(
        encoding="utf-8"
    )

    assert "transition_execution_row(" in bybit_reconciler
    assert "transition_execution_row(" in mt5_reconciler
    assert "transition_execution_row(" in bybit_router

    mark_block = bybit_reconciler[
        bybit_reconciler.index("async def _mark("):
        bybit_reconciler.index("async def reconcile_bybit_executions_once"),
    ]
    assert "row.status = str(status)" not in mark_block

    mt5_block = mt5_reconciler[
        mt5_reconciler.index("async def _persist_reconciliation("):
        mt5_reconciler.index("async def reconcile_mt5_executions_once"),
    ]
    assert 'row.status = "open"' not in mt5_block
    assert 'row.status = "closed"' not in mt5_block
