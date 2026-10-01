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

import json
import logging
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Protocol

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
        self,
        *,
        entry_id: str,
        event_type: str,
        partition_key: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        occurred_at: str,
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
        self,
        *,
        entry_id: str,
        event_type: str,
        partition_key: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        occurred_at: str,
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
            entry_id=entry.entry_id,
            event_type=entry.event_type,
            partition_key=entry.partition_key,
            payload=entry.payload,
            idempotency_key=entry.idempotency_key,
            occurred_at=entry.occurred_at,
            status="done",
            attempts=entry.attempts,
            last_error=entry.last_error,
        )

    async def mark_failed(self, entry_id: str, error: str, *, attempts: int) -> None:
        entry = self._entries.get(entry_id)
        if entry is None:
            return
        self._entries[entry_id] = OutboxEntry(
            entry_id=entry.entry_id,
            event_type=entry.event_type,
            partition_key=entry.partition_key,
            payload=entry.payload,
            idempotency_key=entry.idempotency_key,
            occurred_at=entry.occurred_at,
            status="failed",
            attempts=max(1, int(attempts)),
            last_error=str(error)[:512],
        )

    async def dead_letter(self, entry_id: str, reason: str) -> None:
        entry = self._entries.get(entry_id)
        if entry is None:
            return
        self._entries[entry_id] = OutboxEntry(
            entry_id=entry.entry_id,
            event_type=entry.event_type,
            partition_key=entry.partition_key,
            payload=entry.payload,
            idempotency_key=entry.idempotency_key,
            occurred_at=entry.occurred_at,
            status="dead_lettered",
            attempts=entry.attempts,
            last_error=str(reason)[:512],
        )

    async def release_claim(self, entry_id: str) -> None:
        """Return a claimed-but-unprocessed entry to the pending pool."""
        entry = self._entries.get(entry_id)
        if entry is None or entry.status != "claimed":
            return
        self._entries[entry_id] = OutboxEntry(
            entry_id=entry.entry_id,
            event_type=entry.event_type,
            partition_key=entry.partition_key,
            payload=entry.payload,
            idempotency_key=entry.idempotency_key,
            occurred_at=entry.occurred_at,
            status="pending",
            attempts=entry.attempts,
            last_error=entry.last_error,
        )

    async def depth(self) -> int:
        return sum(1 for entry in self._entries.values() if entry.status in ("pending", "claimed", "failed"))


class PostgresTransactionalOutbox:
    """PostgreSQL-backed outbox used by production/staging event recovery.

    Claims are short database transactions using FOR UPDATE SKIP LOCKED.
    Network publication happens only after claim returns, so Redis/network
    latency never extends the database transaction.
    """

    def __init__(self, *, lease_seconds: int = 60) -> None:
        self.lease_seconds = max(5, min(3600, int(lease_seconds)))

    @staticmethod
    def _entry(row: Mapping[str, Any]) -> OutboxEntry:
        payload = row.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {"raw": payload}
        occurred = row.get("occurred_at")
        if isinstance(occurred, datetime):
            occurred_at = occurred.astimezone(timezone.utc).isoformat() if occurred.tzinfo else occurred.replace(tzinfo=timezone.utc).isoformat()
        else:
            occurred_at = str(occurred or "")
        return OutboxEntry(
            entry_id=str(row.get("entry_id") or ""),
            event_type=str(row.get("event_type") or ""),
            partition_key=str(row.get("partition_key") or ""),
            payload=dict(payload),
            idempotency_key=str(row.get("idempotency_key") or ""),
            occurred_at=occurred_at,
            status=str(row.get("status") or "pending"),
            attempts=int(row.get("attempts") or 0),
            last_error=str(row.get("last_error")) if row.get("last_error") is not None else None,
        )

    async def enqueue(
        self,
        *,
        entry_id: str,
        event_type: str,
        partition_key: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        occurred_at: str,
    ) -> OutboxEntry:
        from sqlalchemy import text
        from db.session import get_session

        encoded = json.dumps(dict(payload), separators=(",", ":"), default=str)
        async with get_session(
            priority="critical",
            label="event_outbox.enqueue",
            timeout_seconds=3.0,
            drop_if_busy=False,
        ) as session:
            result = await session.execute(
                text(
                    """
                    INSERT INTO event_outbox(
                        entry_id,event_type,partition_key,payload,idempotency_key,
                        occurred_at,status,attempts,available_at,created_at,updated_at
                    )
                    VALUES(
                        :entry_id,:event_type,:partition_key,CAST(:payload AS JSONB),
                        :idempotency_key,CAST(:occurred_at AS TIMESTAMPTZ),
                        'pending',0,NOW(),NOW(),NOW()
                    )
                    ON CONFLICT(idempotency_key) DO UPDATE
                    SET updated_at=event_outbox.updated_at
                    RETURNING *
                    """
                ),
                {
                    "entry_id": str(entry_id),
                    "event_type": str(event_type),
                    "partition_key": str(partition_key),
                    "payload": encoded,
                    "idempotency_key": str(idempotency_key),
                    "occurred_at": str(occurred_at),
                },
            )
            row = result.mappings().one()
            await session.commit()
        return self._entry(row)

    async def claim(self, *, batch: int = 10) -> list[OutboxEntry]:
        from sqlalchemy import text
        from db.session import get_session

        async with get_session(
            priority="background",
            label="event_outbox.claim",
            timeout_seconds=2.0,
            drop_if_busy=True,
        ) as session:
            result = await session.execute(
                text(
                    """
                    WITH candidate AS (
                        SELECT entry_id
                        FROM event_outbox
                        WHERE (
                            status IN ('pending','failed') AND available_at <= NOW()
                        ) OR (
                            status='claimed'
                            AND claimed_at < NOW() - (:lease_seconds * INTERVAL '1 second')
                        )
                        ORDER BY created_at, entry_id
                        FOR UPDATE SKIP LOCKED
                        LIMIT :batch
                    )
                    UPDATE event_outbox AS e
                    SET status='claimed', claimed_at=NOW(), updated_at=NOW()
                    FROM candidate c
                    WHERE e.entry_id=c.entry_id
                    RETURNING e.*
                    """
                ),
                {"lease_seconds": self.lease_seconds, "batch": max(1, min(100, int(batch)))},
            )
            rows = list(result.mappings().all())
            await session.commit()
        return [self._entry(row) for row in rows]

    async def mark_done(self, entry_id: str) -> None:
        await self._update_status(entry_id, "done")

    async def mark_failed(self, entry_id: str, error: str, *, attempts: int) -> None:
        from sqlalchemy import text
        from db.session import get_session

        attempts = max(1, int(attempts))
        async with get_session(
            priority="background",
            label="event_outbox.failed",
            timeout_seconds=2.0,
            drop_if_busy=False,
        ) as session:
            await session.execute(
                text(
                    """
                    UPDATE event_outbox
                    SET status='failed',
                        attempts=:attempts,
                        last_error=:error,
                        claimed_at=NULL,
                        available_at=NOW() + (
                            LEAST(300, POWER(2, GREATEST(:attempts - 1, 0))) * INTERVAL '1 second'
                        ),
                        updated_at=NOW()
                    WHERE entry_id=:entry_id
                    """
                ),
                {"entry_id": str(entry_id), "attempts": attempts, "error": str(error)[:512]},
            )
            await session.commit()

    async def dead_letter(self, entry_id: str, reason: str) -> None:
        from sqlalchemy import text
        from db.session import get_session

        async with get_session(
            priority="background",
            label="event_outbox.dead_letter",
            timeout_seconds=2.0,
            drop_if_busy=False,
        ) as session:
            await session.execute(
                text(
                    """
                    UPDATE event_outbox
                    SET status='dead_lettered', last_error=:reason,
                        claimed_at=NULL, updated_at=NOW()
                    WHERE entry_id=:entry_id
                    """
                ),
                {"entry_id": str(entry_id), "reason": str(reason)[:512]},
            )
            await session.commit()

    async def release_claim(self, entry_id: str) -> None:
        await self._update_status(entry_id, "pending", clear_claim=True)

    async def _update_status(self, entry_id: str, status: str, *, clear_claim: bool = True) -> None:
        from sqlalchemy import text
        from db.session import get_session

        async with get_session(
            priority="background",
            label="event_outbox.status",
            timeout_seconds=2.0,
            drop_if_busy=False,
        ) as session:
            await session.execute(
                text(
                    """
                    UPDATE event_outbox
                    SET status=:status,
                        claimed_at=CASE WHEN :clear_claim THEN NULL ELSE claimed_at END,
                        updated_at=NOW()
                    WHERE entry_id=:entry_id
                    """
                ),
                {"entry_id": str(entry_id), "status": str(status), "clear_claim": bool(clear_claim)},
            )
            await session.commit()

    async def depth(self) -> int:
        from sqlalchemy import text
        from db.session import get_session

        async with get_session(
            priority="background",
            label="event_outbox.depth",
            timeout_seconds=1.0,
            drop_if_busy=True,
        ) as session:
            value = (
                await session.execute(
                    text(
                        "SELECT COUNT(*) FROM event_outbox "
                        "WHERE status IN ('pending','claimed','failed')"
                    )
                )
            ).scalar_one()
            await session.rollback()
        return int(value or 0)


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
    "PostgresTransactionalOutbox",
    "OutboxClaim",
    "OutboxEntry",
    "OutboxRelay",
    "TransactionalOutbox",
]
