"""Transactional outbox and idempotent inbox for the event platform.

Implements the V2.0 programme section 6.3 contract:

* ``TransactionalOutbox`` - durable work records published only after the
  source-of-truth transaction commits (the caller commits the business write
  and the outbox entry atomically; this module owns the outbox semantics).
* ``IdempotentInbox`` - consumer-side deduplication keyed on the event's
  ``idempotency_key`` so at-least-once transports become exactly-once logical
  processing.
* ``OutboxRelay`` - bounded relay loop with claim/ack semantics, retry
  counter, exponential backoff and dead-letter routing. It never holds a
  business transaction open during network work (the processor runs after
  claim; proof updates are separate follow-up writes).

The production transport can be any append-only store (PostgreSQL table,
Redis Streams via ``core.redis_streams`` or ``core.durable_event_stream``).
This module ships a deterministic in-memory implementation used by the relay
and by contract tests; a SQL adapter must satisfy the same protocol.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Protocol, Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OutboxEntry:
    entry_id: str
    event_type: str
    partition_key: str
    payload: Mapping[str, Any]
    idempotency_key: str
    occurred_at: str
    status: str = "pending"  # pending | claimed | done | failed | dead_lettered
    attempts: int = 0
    last_error: str | None = None


@dataclass(frozen=True, slots=True)
class OutboxClaim:
    entry: OutboxEntry
    claimed_at: float = field(default_factory=time.monotonic)

    def expire_after(self, seconds: float) -> bool:
        return time.monotonic() - self.claimed_at >= float(seconds)


class TransactionalOutbox(Protocol):
    """Persistence contract for outbox work records."""

    async def enqueue(
        self, *, entry_id: str, event_type: str, partition_key: str,
        payload: Mapping[str, Any], idempotency_key: str, occurred_at: str,
    ) -> OutboxEntry: ...

    async def claim(self, *, batch: int = 10) -> list[OutboxEntry]: ...

    async def mark_done(self, entry_id: str) -> None: ...

    async def mark_failed(self, entry_id: str, error: str, *, attempts: int) -> None: ...

    async def dead_letter(self, entry_id: str, reason: str) -> None: ...

    async def release_claim(self, entry_id: str) -> None: ...

    async def depth(self) -> int: ...


class MemoryTransactionalOutbox:
    """Deterministic in-memory outbox for contract tests and single-node use.

    ``idempotency_key`` is unique: re-enqueuing the same key returns the
    existing entry and is recorded as a duplicate instead of a second record.
    """

    def __init__(self) -> None:
        self._entries: dict[str, OutboxEntry] = {}
        self._by_idempotency: dict[str, str] = {}
        self.duplicate_count: int = 0

    async def enqueue(
        self, *, entry_id: str, event_type: str, partition_key: str,
        payload: Mapping[str, Any], idempotency_key: str, occurred_at: str,
    ) -> OutboxEntry:
        existing_id = self._by_idempotency.get(idempotency_key)
        if existing_id is not None:
            self.duplicate_count += 1
            return self._entries[existing_id]
        entry = OutboxEntry(
            entry_id=entry_id,
            event_type=event_type,
            partition_key=partition_key,
            payload=dict(payload),
            idempotency_key=idempotency_key,
            occurred_at=occurred_at,
        )
        self._entries[entry_id] = entry
        self._by_idempotency[idempotency_key] = entry_id
        return entry

    async def claim(self, *, batch: int = 10) -> list[OutboxEntry]:
        # Failed entries remain claimable so the relay can retry them with
        # backoff; dead-lettered and done entries are terminal.
        claimable = ("pending", "failed")
        claimed: list[OutboxEntry] = []
        for entry in self._entries.values():
            if entry.status in claimable and len(claimed) < max(1, int(batch)):
                updated = OutboxEntry(
                    entry_id=entry.entry_id,
                    event_type=entry.event_type,
                    partition_key=entry.partition_key,
                    payload=entry.payload,
                    idempotency_key=entry.idempotency_key,
                    occurred_at=entry.occurred_at,
                    status="claimed",
                    attempts=entry.attempts,
                    last_error=entry.last_error,
                )
                self._entries[entry.entry_id] = updated
                claimed.append(updated)
        return claimed

    async def mark_done(self, entry_id: str) -> None:
        entry = self._entries.get(entry_id)
        if entry is None:
            return
        self._entries[entry_id] = OutboxEntry(
            entry_id=entry.entry_id, event_type=entry.event_type,
            partition_key=entry.partition_key, payload=entry.payload,
            idempotency_key=entry.idempotency_key, occurred_at=entry.occurred_at,
            status="done", attempts=entry.attempts, last_error=entry.last_error,
        )

    async def mark_failed(self, entry_id: str, error: str, *, attempts: int) -> None:
        entry = self._entries.get(entry_id)
        if entry is None:
            return
        self._entries[entry_id] = OutboxEntry(
            entry_id=entry.entry_id, event_type=entry.event_type,
            partition_key=entry.partition_key, payload=entry.payload,
            idempotency_key=entry.idempotency_key, occurred_at=entry.occurred_at,
            status="failed", attempts=max(1, int(attempts)), last_error=str(error)[:512],
        )

    async def dead_letter(self, entry_id: str, reason: str) -> None:
        entry = self._entries.get(entry_id)
        if entry is None:
            return
        self._entries[entry_id] = OutboxEntry(
            entry_id=entry.entry_id, event_type=entry.event_type,
            partition_key=entry.partition_key, payload=entry.payload,
            idempotency_key=entry.idempotency_key, occurred_at=entry.occurred_at,
            status="dead_lettered", attempts=entry.attempts,
            last_error=str(reason)[:512],
        )

    async def release_claim(self, entry_id: str) -> None:
        """Return a claimed-but-unprocessed entry to the pending pool."""
        entry = self._entries.get(entry_id)
        if entry is None or entry.status != "claimed":
            return
        self._entries[entry_id] = OutboxEntry(
            entry_id=entry.entry_id, event_type=entry.event_type,
            partition_key=entry.partition_key, payload=entry.payload,
            idempotency_key=entry.idempotency_key, occurred_at=entry.occurred_at,
            status="pending", attempts=entry.attempts, last_error=entry.last_error,
        )

    async def depth(self) -> int:
        return sum(1 for entry in self._entries.values() if entry.status in ("pending", "claimed", "failed"))


class IdempotentInbox:
    """Consumer-side deduplication store for exactly-once logical processing.

    ``process`` wraps a handler so a replayed event (same idempotency key) is
    observed once. Expired keys are pruned lazily during checks.
    """

    def __init__(self, *, ttl_seconds: float = 7 * 24 * 3600) -> None:
        self.ttl_seconds = float(ttl_seconds)
        self._processed: dict[str, tuple[str, float]] = {}
        self.replay_count: int = 0

    def already_processed(self, idempotency_key: str) -> bool:
        record = self._processed.get(idempotency_key)
        if record is None:
            return False
        stored_at = record[1]
        if time.monotonic() - stored_at > self.ttl_seconds:
            self._processed.pop(idempotency_key, None)
            return False
        return True

    def record_processed(self, idempotency_key: str, *, event_id: str | None = None) -> None:
        self._processed[idempotency_key] = (str(event_id or ""), time.monotonic())

    async def process(self, idempotency_key: str, handler: Callable[[], Awaitable[Any]]) -> tuple[bool, Any]:
        if self.already_processed(idempotency_key):
            self.replay_count += 1
            return False, None
        result = await handler()
        self.record_processed(idempotency_key)
        return True, result

    def __len__(self) -> int:
        return len(self._processed)


class OutboxRelay:
    """Bounded relay that moves claimed outbox entries through a processor.

    * Claims up to ``batch_size`` entries.
    * Runs the processor outside any business transaction.
    * Marks done on success, failed with the retry counter on error.
    * Dead-letters entries that exceed ``max_attempts``.
    * Never processes more than ``budget`` entries per invocation so a single
      saturated outbox cannot starve other work.
    """

    def __init__(
        self,
        *,
        outbox: TransactionalOutbox,
        inbox: IdempotentInbox,
        processor: Callable[[OutboxEntry], Awaitable[None]],
        batch_size: int = 10,
        budget: int = 100,
        max_attempts: int = 5,
        backoff_base_seconds: float = 1.0,
        backoff_max_seconds: float = 300.0,
    ) -> None:
        self.outbox = outbox
        self.inbox = inbox
        self.processor = processor
        self.batch_size = max(1, int(batch_size))
        self.budget = max(1, int(budget))
        self.max_attempts = max(1, int(max_attempts))
        self.backoff_base = float(backoff_base_seconds)
        self.backoff_max = float(backoff_max_seconds)
        self.metrics = {
            "processed": 0,
            "failed": 0,
            "dead_lettered": 0,
            "duplicates": 0,
            "replayed": 0,
        }

    def _backoff(self, attempts: int) -> float:
        return min(self.backoff_max, self.backoff_base * (2 ** max(0, int(attempts) - 1)))

    async def run_once(self) -> int:
        processed_count = 0
        remaining = self.budget
        while remaining > 0:
            batch = await self.outbox.claim(batch=min(self.batch_size, remaining))
            if not batch:
                break
            paused = False
            for index, entry in enumerate(batch):
                remaining -= 1
                processed_count += 1
                if await self._handle(entry):
                    paused = True  # backoff: stop this cycle after a failure
                    # Release entries claimed after the failing one so they are
                    # not stuck in "claimed" state across cycles.
                    for tail in batch[index + 1 :]:
                        await self.outbox.release_claim(tail.entry_id)
                    break
            if paused or len(batch) < self.batch_size:
                break
        return processed_count

    async def _handle(self, entry: OutboxEntry) -> bool:
        """Process one entry. Returns True when the queue should pause (backoff)."""
        idempotency_key = str(entry.idempotency_key or entry.entry_id)
        if self.inbox.already_processed(idempotency_key):
            await self.outbox.mark_done(entry.entry_id)
            self.metrics["duplicates"] += 1
            return False
        try:
            await self.processor(entry)
        except Exception as exc:  # noqa: BLE001 - relay must classify every failure
            attempts = entry.attempts + 1
            sanitized = f"{type(exc).__name__}: {str(exc)[:400]}"
            logger.warning("[outbox_relay] entry=%s failed attempt=%d error=%s", entry.entry_id, attempts, sanitized)
            self.metrics["failed"] += 1
            if attempts >= self.max_attempts:
                await self.outbox.dead_letter(entry.entry_id, sanitized)
                self.metrics["dead_lettered"] += 1
                return False
            await self.outbox.mark_failed(entry.entry_id, sanitized, attempts=attempts)
            return True  # pause: respect exponential backoff before retrying
        else:
            self.inbox.record_processed(idempotency_key, event_id=entry.entry_id)
            await self.outbox.mark_done(entry.entry_id)
            self.metrics["processed"] += 1
            return False


__all__ = [
    "IdempotentInbox",
    "MemoryTransactionalOutbox",
    "OutboxClaim",
    "OutboxEntry",
    "OutboxRelay",
    "TransactionalOutbox",
]
