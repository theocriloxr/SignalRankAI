"""Regression tests: V2.0 event envelope, catalogue, outbox/inbox/relay."""
from __future__ import annotations

import pytest

from core.durable_event_stream import EventEnvelope
from core.event_catalogue import (
    AggregateType,
    all_event_types,
    events_for_aggregate,
    validate_event_type,
)
from core.transactional_outbox import (
    IdempotentInbox,
    MemoryTransactionalOutbox,
    OutboxRelay,
)


# ── Envelope ────────────────────────────────────────────────────────────────

def test_envelope_computes_and_verifies_payload_hash() -> None:
    envelope = EventEnvelope("SignalGenerated", {"a": 1}, "BTCUSDT")
    assert envelope.payload_hash
    assert envelope.verify_payload_hash()


def test_envelope_tamper_evidence_detects_payload_mutation() -> None:
    payload: dict = {"a": 1}
    envelope = EventEnvelope("SignalGenerated", payload, "BTCUSDT")
    payload["a"] = 999
    assert not envelope.verify_payload_hash()


def test_envelope_full_identity_fields() -> None:
    envelope = EventEnvelope(
        "OrderFilled",
        {"qty": 1},
        "user:42",
        aggregate_type="order",
        aggregate_id="ord-1",
        organization_id="org-7",
        strategy_id="strat-1",
        provider="bybit",
        venue="bybit",
        trace_id="trace-1",
        deployment_id="dep-1",
        producer_service="execution",
        idempotency_key="ik-1",
    )
    assert envelope.aggregate_type == "order"
    assert envelope.producer_service == "execution"
    assert envelope.verify_payload_hash()


def test_envelope_rejects_empty_identity() -> None:
    with pytest.raises(ValueError):
        EventEnvelope("", {"a": 1}, "BTCUSDT")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        EventEnvelope("SignalGenerated", {"a": 1}, "")


# ── Catalogue ───────────────────────────────────────────────────────────────

def test_catalogue_accepts_core_event_types() -> None:
    assert validate_event_type("SignalGenerated") == "SignalGenerated"
    assert validate_event_type("OutcomeFinalized") == "OutcomeFinalized"


def test_catalogue_rejects_unknown_event_types() -> None:
    with pytest.raises(ValueError):
        validate_event_type("NotARealEvent")


def test_catalogue_aggregate_grouping() -> None:
    outcome_events = set(events_for_aggregate(AggregateType.OUTCOME))
    assert {"TP1Reached", "TP3Reached", "OutcomeFinalized"} <= outcome_events
    assert "SignalGenerated" in all_event_types()
    assert len(all_event_types()) >= 40  # full V2.0 section 6.1 core list


# ── Outbox ──────────────────────────────────────────────────────────────────

async def _seed(outbox: MemoryTransactionalOutbox, key: str) -> None:
    await outbox.enqueue(
        entry_id=f"e-{key}",
        event_type="SignalStored",
        partition_key=key,
        payload={"symbol": key},
        idempotency_key=f"ik-{key}",
        occurred_at="2026-08-05T00:00:00+00:00",
    )


async def test_outbox_unique_idempotency_key() -> None:
    outbox = MemoryTransactionalOutbox()
    await _seed(outbox, "BTCUSDT")
    await _seed(outbox, "BTCUSDT")
    assert outbox.duplicate_count == 1
    assert await outbox.depth() == 1


async def test_outbox_claim_only_pending() -> None:
    outbox = MemoryTransactionalOutbox()
    await _seed(outbox, "A")
    await _seed(outbox, "B")
    first = await outbox.claim(batch=1)
    assert len(first) == 1
    assert first[0].status == "claimed"
    second = await outbox.claim(batch=10)
    assert [e.entry_id for e in second] == ["e-B"]


async def test_inbox_exactly_once_processing() -> None:
    inbox = IdempotentInbox()
    calls: list[str] = []

    async def handler() -> None:
        calls.append("ran")

    ran1, _ = await inbox.process("ik-1", handler)
    ran2, _ = await inbox.process("ik-1", handler)
    assert ran1 is True and ran2 is False
    assert calls == ["ran"]
    assert inbox.replay_count == 1


async def test_relay_processes_and_acks() -> None:
    outbox = MemoryTransactionalOutbox()
    inbox = IdempotentInbox()
    processed: list[str] = []

    async def processor(entry) -> None:
        processed.append(entry.entry_id)

    relay = OutboxRelay(outbox=outbox, inbox=inbox, processor=processor)
    for key in ("A", "B", "C"):
        await _seed(outbox, key)
    count = await relay.run_once()
    assert count == 3
    assert sorted(processed) == ["e-A", "e-B", "e-C"]
    assert await outbox.depth() == 0
    assert relay.metrics["processed"] == 3


async def test_relay_dead_letters_after_max_attempts() -> None:
    outbox = MemoryTransactionalOutbox()
    inbox = IdempotentInbox()

    async def failing(entry) -> None:
        raise RuntimeError("boom")

    relay = OutboxRelay(
        outbox=outbox,
        inbox=inbox,
        processor=failing,
        max_attempts=2,
        batch_size=1,
    )
    await _seed(outbox, "A")
    # First run fails (attempt 1) and pauses for backoff; the entry remains
    # claimable. Second run fails again (attempt 2) and dead-letters it.
    assert await relay.run_once() == 1
    assert await relay.run_once() == 1
    assert relay.metrics["failed"] == 2
    assert relay.metrics["dead_lettered"] == 1
    assert await outbox.depth() == 0  # dead-lettered entries are terminal


async def test_relay_budget_bounds_work() -> None:
    outbox = MemoryTransactionalOutbox()
    inbox = IdempotentInbox()
    processed: list[str] = []

    async def processor(entry) -> None:
        processed.append(entry.entry_id)

    relay = OutboxRelay(outbox=outbox, inbox=inbox, processor=processor, budget=2)
    for key in ("A", "B", "C", "D", "E"):
        await _seed(outbox, key)
    assert await relay.run_once() == 2
    assert len(processed) == 2
    # Remaining work is still pending for the next cycle.
    assert await outbox.depth() == 3


async def test_relay_releases_unprocessed_tail_after_mid_batch_failure() -> None:
    """Entries claimed after a failing entry must return to pending."""
    outbox = MemoryTransactionalOutbox()
    inbox = IdempotentInbox()
    calls: list[str] = []

    async def processor(entry) -> None:
        if entry.entry_id == "e-B":
            raise RuntimeError("boom")
        calls.append(entry.entry_id)

    relay = OutboxRelay(
        outbox=outbox,
        inbox=inbox,
        processor=processor,
        max_attempts=2,  # B fails retryably on the first cycle (backoff pause)
        batch_size=3,
    )
    for key in ("A", "B", "C"):
        await _seed(outbox, key)
    await relay.run_once()
    # A processed; B failed retryably (pause); C must NOT be stuck "claimed".
    assert sorted(calls) == ["e-A"]
    assert relay.metrics["dead_lettered"] == 0
    # Next cycle: B dead-letters (terminal) and C is still claimable.
    count = await relay.run_once()
    assert count == 2
    assert relay.metrics["dead_lettered"] == 1
    assert sorted(calls) == ["e-A", "e-C"]


async def test_relay_skips_already_processed_duplicates() -> None:
    outbox = MemoryTransactionalOutbox()
    inbox = IdempotentInbox()
    calls: list[str] = []
    inbox.record_processed("ik-A")

    async def processor(entry) -> None:
        calls.append(entry.entry_id)

    relay = OutboxRelay(outbox=outbox, inbox=inbox, processor=processor)
    await _seed(outbox, "A")
    await relay.run_once()
    assert calls == []
    assert relay.metrics["duplicates"] == 1
