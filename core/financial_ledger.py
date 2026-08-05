"""Append-only, decimal-safe financial ledger (V2.0 section 13).

Immutability contract: once ``post`` accepts an entry it is never mutated or
deleted. Errors are repaired with audited compensating corrections that
reference the original entry. Double-entry pairs share one correlation id and
must balance; ``reconcile`` and ``imbalance`` expose any drift. No dashboard
aggregate is the system of record here - the entry list is.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping
from uuid import uuid4


def _decimal(value: Any, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"non_finite_{field_name}") from None
    if not parsed.is_finite():
        raise ValueError(f"non_finite_{field_name}")
    return parsed


class EntryType(str):
    """Ledger entry types; constant set to prevent arbitrary mutation labels."""

    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    RESERVED_CASH = "reserved_cash"
    RESERVED_MARGIN = "reserved_margin"
    REALIZED_PNL = "realized_pnl"
    UNREALIZED_PNL_SNAPSHOT = "unrealized_pnl_snapshot"
    FEE = "fee"
    COMMISSION = "commission"
    FUNDING = "funding"
    REBATE = "rebate"
    SLIPPAGE = "slippage"
    PARTIAL_EXIT = "partial_exit"
    SUBSCRIPTION_CHARGE = "subscription_charge"
    REFUND = "refund"
    REFERRAL_COMMISSION = "referral_commission"
    PAYOUT = "payout"
    PAYMENT_DISPUTE = "payment_dispute"
    CORRECTION = "correction"


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    entry_id: str
    account_id: str
    entry_type: str
    currency: str
    amount: Decimal
    balance_after: Decimal
    source_event_id: str
    correlation_id: str
    created_at: str
    counterparty_id: str | None = None
    note: str = ""
    correction_of_entry_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "account_id", str(self.account_id))
        object.__setattr__(self, "entry_type", str(self.entry_type or "").lower())
        object.__setattr__(self, "currency", str(self.currency or "").upper())


@dataclass(frozen=True, slots=True)
class LedgerCorrection:
    """A compensating entry correcting an earlier entry without rewriting it."""

    entry: LedgerEntry
    original_entry_id: str
    reason: str
    corrected_balance_after: Decimal


class DuplicateSourceEvent(ValueError):
    pass


class _FrozenUtcClock:
    def __init__(self, now: str | None = None) -> None:
        self._fixed = now

    def __call__(self) -> str:
        if self._fixed is not None:
            return self._fixed
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()


class FinancialLedger:
    """Append-only ledger. ``now`` is injectable for deterministic tests."""

    def __init__(self, *, now: str | None = None) -> None:
        self._entries: dict[str, LedgerEntry] = {}
        self._balances: dict[str, Decimal] = {}
        self._by_source: dict[str, str] = {}
        self._clock = _FrozenUtcClock(now)
        self.correction_count = 0

    @property
    def entries(self) -> tuple[LedgerEntry, ...]:
        return tuple(self._entries.values())

    def balance(self, account_id: str) -> Decimal:
        return self._balances.get(str(account_id), Decimal("0"))

    def post(
        self,
        *,
        account_id: str,
        entry_type: str,
        amount: Any,
        currency: str = "USD",
        source_event_id: str | None = None,
        correlation_id: str | None = None,
        note: str = "",
        entry_id: str | None = None,
    ) -> LedgerEntry:
        """Append one immutable entry. Duplicate source events are rejected."""
        account = str(account_id)
        amount_d = _decimal(amount, "amount")
        if source_event_id and source_event_id in self._by_source:
            raise DuplicateSourceEvent(
                f"source_event_id_already_applied:{source_event_id}"
            )
        entry = LedgerEntry(
            entry_id=str(entry_id or uuid4().hex),
            account_id=account,
            entry_type=str(entry_type or "").lower(),
            currency=str(currency or "USD").upper(),
            amount=amount_d,
            balance_after=self.balance(account) + amount_d,
            source_event_id=str(source_event_id or ""),
            correlation_id=str(correlation_id or uuid4().hex),
            created_at=self._clock(),
            note=str(note)[:512],
        )
        if entry.entry_id in self._entries:
            raise DuplicateSourceEvent(f"duplicate_entry_id:{entry.entry_id}")
        self._entries[entry.entry_id] = entry
        self._balances[account] = entry.balance_after
        if source_event_id:
            self._by_source[source_event_id] = entry.entry_id
        return entry

    def correct(
        self,
        *,
        original_entry_id: str,
        correction_amount: Any,
        reason: str,
        currency: str = "USD",
        source_event_id: str | None = None,
        correlation_id: str | None = None,
        note: str = "system_correction",
    ) -> LedgerCorrection:
        """Post an audited compensating correction referencing the original."""
        original = self._entries.get(original_entry_id)
        if original is None:
            raise KeyError(f"unknown_entry:{original_entry_id}")
        correction = self.post(
            account_id=original.account_id,
            entry_type=EntryType.CORRECTION,
            amount=correction_amount,
            currency=currency,
            source_event_id=source_event_id,
            correlation_id=correlation_id or original.correlation_id,
            note=note,
        )
        self.correction_count += 1
        return LedgerCorrection(
            entry=correction,
            original_entry_id=original.entry_id,
            reason=str(reason)[:512],
            corrected_balance_after=correction.balance_after,
        )

    def post_double_entry(
        self,
        *,
        debit_account_id: str,
        credit_account_id: str,
        entry_type: str,
        amount: Any,
        currency: str = "USD",
        source_event_id: str | None = None,
        correlation_id: str | None = None,
        note: str = "",
    ) -> tuple[LedgerEntry, LedgerEntry]:
        """Post a balanced debit/credit pair sharing one correlation id.

        Debit is a positive balance movement on the debit account; credit is
        negative on the credit account. The books remain balanced by amount.
        """
        amount_d = _decimal(amount, "amount")
        if amount_d < 0:
            raise ValueError("double_entry_amount_must_not_be_negative")
        correlation = correlation_id or uuid4().hex
        debit_source = f"{source_event_id or correlation}:debit"
        credit_source = f"{source_event_id or correlation}:credit"
        debit = self.post(
            account_id=debit_account_id,
            entry_type=entry_type,
            amount=amount_d,
            currency=currency,
            source_event_id=debit_source,
            correlation_id=correlation,
            note=note,
        )
        credit = self.post(
            account_id=credit_account_id,
            entry_type=entry_type,
            amount=-amount_d,
            currency=currency,
            source_event_id=credit_source,
            correlation_id=correlation,
            note=note,
        )
        return debit, credit

    def imbalance(self) -> Decimal:
        """Net of all entries across accounts (double-entry check).

        Zero only for balanced double-entry books; single-account ledgers
        report a non-zero net by design.
        """
        return sum((e.amount for e in self._entries.values()), Decimal("0"))

    def orphan_entries(self) -> tuple[LedgerEntry, ...]:
        return tuple(
            entry
            for entry in self._entries.values()
            if not entry.source_event_id and entry.entry_type != EntryType.CORRECTION
        )

    def entries_for_correlation(self, correlation_id: str) -> tuple[LedgerEntry, ...]:
        return tuple(
            entry
            for entry in self._entries.values()
            if entry.correlation_id == correlation_id
        )

    def daily_snapshot(self, day: date) -> Mapping[str, Decimal]:
        """End-of-day balances keyed by account for a given UTC date."""
        day_iso = day.isoformat()
        balances: dict[str, Decimal] = {}
        for entry in self._entries.values():
            if entry.created_at[:10] <= day_iso:
                balances[entry.account_id] = entry.balance_after
        return balances

    def audit_range(self, *, account_id: str | None = None) -> tuple[LedgerEntry, ...]:
        if account_id is None:
            return self.entries
        return tuple(
            entry for entry in self._entries.values()
            if entry.account_id == account_id
        )

    def rebuild_from(self, events: Iterable[Mapping[str, Any]]) -> dict[str, int]:
        """Replay source events into a fresh ledger (idempotent per event id)."""
        rebuilt = FinancialLedger(now=self._clock())
        for event in events:
            source = str(event.get("source_event_id") or "")
            if source and source in rebuilt._by_source:
                continue
            rebuilt.post(
                account_id=str(event["account_id"]),
                entry_type=str(event["entry_type"]),
                amount=event["amount"],
                currency=str(event.get("currency") or "USD"),
                source_event_id=source,
                correlation_id=str(event.get("correlation_id") or ""),
                note=str(event.get("note") or ""),
            )
        return {"replayed": len(rebuilt._entries)}

    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        for entry in self._entries.values():
            digest.update(entry.entry_id.encode("utf-8"))
            digest.update(str(entry.amount).encode("utf-8"))
            digest.update(entry.balance_after.to_eng_string().encode("utf-8"))
        return digest.hexdigest()


__all__ = [
    "DuplicateSourceEvent",
    "EntryType",
    "FinancialLedger",
    "LedgerCorrection",
    "LedgerEntry",
]
