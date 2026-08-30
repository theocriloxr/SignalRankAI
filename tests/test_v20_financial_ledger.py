"""Regression tests: V2.0 append-only financial ledger."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.financial_ledger import (
    DuplicateSourceEvent,
    EntryType,
    FinancialLedger,
)


def _ledger() -> FinancialLedger:
    return FinancialLedger(now="2026-08-05T12:00:00+00:00")


def test_post_updates_balance_and_is_immutable() -> None:
    ledger = _ledger()
    entry = ledger.post(
        account_id="acc-1",
        entry_type=EntryType.DEPOSIT,
        amount=Decimal("1000"),
        source_event_id="evt-deposit-1",
    )
    assert ledger.balance("acc-1") == Decimal("1000")
    assert entry.balance_after == Decimal("1000")
    with pytest.raises(Exception):
        entry.amount = Decimal("999")  # frozen dataclass must reject mutation


def test_decimal_precision_preserved() -> None:
    ledger = _ledger()
    ledger.post(account_id="a", entry_type=EntryType.DEPOSIT, amount="0.1", source_event_id="e1")
    ledger.post(account_id="a", entry_type=EntryType.DEPOSIT, amount="0.2", source_event_id="e2")
    assert ledger.balance("a") == Decimal("0.3")


def test_duplicate_source_event_rejected() -> None:
    ledger = _ledger()
    ledger.post(account_id="a", entry_type=EntryType.DEPOSIT, amount="1", source_event_id="dup")
    with pytest.raises(DuplicateSourceEvent):
        ledger.post(account_id="a", entry_type=EntryType.DEPOSIT, amount="2", source_event_id="dup")


def test_correction_posts_compensating_entry() -> None:
    ledger = _ledger()
    original = ledger.post(
        account_id="a", entry_type=EntryType.REALIZED_PNL,
        amount=Decimal("100"), source_event_id="pnl-1",
    )
    correction = ledger.correct(
        original_entry_id=original.entry_id,
        correction_amount=Decimal("-100"),
        reason="duplicate_excluded",
    )
    assert correction.original_entry_id == original.entry_id
    assert ledger.balance("a") == Decimal("0")
    assert correction.entry.entry_type == EntryType.CORRECTION
    assert ledger.correction_count == 1


def test_double_entry_balances() -> None:
    ledger = _ledger()
    debit, credit = ledger.post_double_entry(
        debit_account_id="cash",
        credit_account_id="revenue",
        entry_type=EntryType.SUBSCRIPTION_CHARGE,
        amount=Decimal("50"),
        correlation_id="corr-1",
    )
    assert debit.amount == Decimal("50")
    assert credit.amount == Decimal("-50")
    assert ledger.imbalance() == Decimal("0")
    assert len(ledger.entries_for_correlation("corr-1")) == 2


def test_double_entry_rejects_negative_amount() -> None:
    ledger = _ledger()
    with pytest.raises(ValueError):
        ledger.post_double_entry(
            debit_account_id="a", credit_account_id="b",
            entry_type=EntryType.FEE, amount=Decimal("-5"),
        )


def test_orphan_detection() -> None:
    ledger = _ledger()
    ledger.post(account_id="a", entry_type=EntryType.DEPOSIT, amount="1")  # no source event
    ledger.post(account_id="a", entry_type=EntryType.FEE, amount="-1", source_event_id="e")
    orphans = ledger.orphan_entries()
    assert len(orphans) == 1
    assert orphans[0].source_event_id == ""


def test_daily_snapshot() -> None:
    ledger = _ledger()
    ledger.post(account_id="a", entry_type=EntryType.DEPOSIT, amount="100", source_event_id="e1")
    snapshot = ledger.daily_snapshot(date(2026, 8, 5))
    assert snapshot["a"] == Decimal("100")
    assert ledger.daily_snapshot(date(2026, 8, 4)) == {}


def test_rebuild_is_idempotent() -> None:
    events = [
        {
            "account_id": "a",
            "entry_type": EntryType.DEPOSIT,
            "amount": "100",
            "source_event_id": "evt-1",
        },
        {
            "account_id": "a",
            "entry_type": EntryType.FEE,
            "amount": "-10",
            "source_event_id": "evt-2",
        },
    ]
    rebuilt = FinancialLedger().rebuild_from(events)
    assert rebuilt["replayed"] == 2
    second = FinancialLedger().rebuild_from(events)
    assert second["replayed"] == 2  # identical, deterministic replay


def test_fingerprint_changes_when_entries_change() -> None:
    ledger = _ledger()
    ledger.post(account_id="a", entry_type=EntryType.DEPOSIT, amount="1", source_event_id="e1")
    before = ledger.fingerprint()
    ledger.post(account_id="a", entry_type=EntryType.DEPOSIT, amount="2", source_event_id="e2")
    assert ledger.fingerprint() != before


def test_rejects_non_finite_amounts() -> None:
    ledger = _ledger()
    with pytest.raises(ValueError):
        ledger.post(account_id="a", entry_type=EntryType.DEPOSIT, amount="NaN")
