"""Partitioned durable event transport for the SignalRankAI scale programme.

This module is deliberately feature-flagged and is not wired into live order or
notification paths in v1.3.6.8. It provides the production contract needed to
migrate database-polling/global loops to replayable Redis Streams without
silently changing current behaviour before staging certification passes.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from uuid import uuid4


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_partition_count(value: int | None = None) -> int:
    raw = value if value is not None else int(os.getenv("DURABLE_EVENT_STREAM_PARTITIONS", "32") or 32)
    return max(1, min(1024, int(raw)))


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    event_type: str
    payload: Mapping[str, Any]
    partition_key: str
    event_id: str = field(default_factory=lambda: str(uuid4()))
    schema_version: int = 1
    occurred_at: str = field(default_factory=_utc_iso)
    tenant_id: str | None = None
    user_id: str | None = None
    broker_account_id: str | None = None
    signal_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    idempotency_key: str | None = None
    producer: str = "unknown"

    def __post_init__(self) -> None:
        if not str(self.event_type or "").strip():
            raise ValueError("event_type is required")
        if not str(self.partition_key or "").strip():
            raise ValueError("partition_key is required")
        if int(self.schema_version) < 1:
            raise ValueError("schema_version must be >= 1")

    def as_stream_fields(self) -> dict[str, str]:
        body = asdict(self)
        payload = body.pop("payload")
        return {
            "event_id": str(body["event_id"]),
            "event_type": str(body["event_type"]),
            "schema_version": str(body["schema_version"]),
            "occurred_at": str(body["occurred_at"]),
            "partition_key": str(body["partition_key"]),
            "metadata": json.dumps(body, sort_keys=True, separators=(",", ":")),
            "payload": json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":")),
        }


@dataclass(frozen=True, slots=True)
class StreamMessage:
    stream: str
    message_id: str
    envelope: EventEnvelope
    delivery_count: int = 1


class DurableEventStreamDisabled(RuntimeError):
    pass


class DurableEventStream:
    """Redis Streams transport with partitioning, consumer groups and DLQ.

    Delivery is at-least-once. Consumers must enforce idempotency using the
    envelope's ``event_id`` or ``idempotency_key`` before committing effects.
    Ordering is preserved only within the same partition key.
    """

    def __init__(
        self,
        *,
        redis_url: str | None = None,
        namespace: str = "signalrankai:events:v2",
        partitions: int | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.redis_url = str(redis_url or os.getenv("EVENT_REDIS_URL") or os.getenv("REDIS_URL") or "").strip()
        self.namespace = str(namespace).strip(":")
        self.partitions = _safe_partition_count(partitions)
        self.enabled = (
            str(os.getenv("DURABLE_EVENT_STREAM_ENABLED", "0")).strip().lower() in {"1", "true", "yes", "on"}
            if enabled is None
            else bool(enabled)
        )
        self._client: Any | None = None

    def partition_for(self, key: str) -> int:
        digest = hashlib.blake2b(str(key).encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big") % self.partitions

    def stream_name(self, partition_key: str) -> str:
        return f"{self.namespace}:p{self.partition_for(partition_key):04d}"

    def dlq_name(self, partition_key: str) -> str:
        return f"{self.namespace}:dlq:p{self.partition_for(partition_key):04d}"

    async def _redis(self):
        if not self.enabled:
            raise DurableEventStreamDisabled("DURABLE_EVENT_STREAM_ENABLED is false")
        if not self.redis_url:
            raise RuntimeError("EVENT_REDIS_URL or REDIS_URL is required")
        if self._client is None:
            from redis.asyncio import Redis

            self._client = Redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=5,
                max_connections=max(4, int(os.getenv("EVENT_REDIS_MAX_CONNECTIONS", "48") or 48)),
                health_check_interval=30,
            )
            await self._client.ping()
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def publish(self, envelope: EventEnvelope, *, maxlen: int | None = None) -> tuple[str, str]:
        client = await self._redis()
        stream = self.stream_name(envelope.partition_key)
        retention = max(1000, int(maxlen or os.getenv("DURABLE_EVENT_STREAM_MAXLEN", "1000000") or 1000000))
        message_id = await client.xadd(stream, envelope.as_stream_fields(), maxlen=retention, approximate=True)
        return stream, str(message_id)

    async def ensure_group(self, group: str, *, start_id: str = "0-0") -> None:
        client = await self._redis()
        for partition in range(self.partitions):
            stream = f"{self.namespace}:p{partition:04d}"
            try:
                await client.xgroup_create(stream, group, id=start_id, mkstream=True)
            except Exception as exc:
                if "BUSYGROUP" not in str(exc):
                    raise

    async def read(
        self,
        *,
        group: str,
        consumer: str,
        partition_keys: Sequence[str] | None = None,
        count: int = 100,
        block_ms: int = 1000,
    ) -> list[StreamMessage]:
        client = await self._redis()
        if partition_keys:
            streams = {self.stream_name(key): ">" for key in partition_keys}
        else:
            streams = {f"{self.namespace}:p{i:04d}": ">" for i in range(self.partitions)}
        response = await client.xreadgroup(
            group,
            consumer,
            streams,
            count=max(1, min(1000, int(count))),
            block=max(0, int(block_ms)),
        )
        messages: list[StreamMessage] = []
        for stream, entries in response or []:
            for message_id, fields in entries:
                messages.append(StreamMessage(
                    stream=str(stream),
                    message_id=str(message_id),
                    envelope=self._decode(fields),
                ))
        return messages

    async def acknowledge(self, *, group: str, message: StreamMessage) -> int:
        client = await self._redis()
        return int(await client.xack(message.stream, group, message.message_id) or 0)

    async def reclaim_stale(
        self,
        *,
        group: str,
        consumer: str,
        stream: str,
        min_idle_ms: int = 60000,
        count: int = 100,
        start_id: str = "0-0",
    ) -> tuple[str, list[StreamMessage]]:
        client = await self._redis()
        next_id, entries, *_ = await client.xautoclaim(
            stream,
            group,
            consumer,
            min_idle_time=max(1000, int(min_idle_ms)),
            start_id=start_id,
            count=max(1, min(1000, int(count))),
        )
        messages = [
            StreamMessage(stream=str(stream), message_id=str(message_id), envelope=self._decode(fields))
            for message_id, fields in entries or []
        ]
        return str(next_id), messages

    async def dead_letter(
        self,
        *,
        group: str,
        message: StreamMessage,
        error_code: str,
        sanitized_error: str,
        attempts: int,
    ) -> str:
        client = await self._redis()
        fields = message.envelope.as_stream_fields()
        fields.update({
            "source_stream": message.stream,
            "source_message_id": message.message_id,
            "consumer_group": group,
            "error_code": str(error_code)[:128],
            "error": str(sanitized_error)[:1000],
            "attempts": str(max(1, int(attempts))),
            "dead_lettered_at": _utc_iso(),
        })
        dlq_id = await client.xadd(
            self.dlq_name(message.envelope.partition_key),
            fields,
            maxlen=max(1000, int(os.getenv("DURABLE_EVENT_DLQ_MAXLEN", "100000") or 100000)),
            approximate=True,
        )
        await client.xack(message.stream, group, message.message_id)
        return str(dlq_id)

    @staticmethod
    def _decode(fields: Mapping[str, Any]) -> EventEnvelope:
        metadata = json.loads(str(fields.get("metadata") or "{}"))
        payload = json.loads(str(fields.get("payload") or "{}"))
        metadata["payload"] = payload
        return EventEnvelope(**metadata)


__all__ = [
    "DurableEventStream",
    "DurableEventStreamDisabled",
    "EventEnvelope",
    "StreamMessage",
]
