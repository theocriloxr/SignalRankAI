"""Recoverable Redis Stream queues for delivery-critical work.

PostgreSQL remains the durable business authority.  These streams provide
bounded, restart-safe work coordination for Telegram updates, delivery
retries, callbacks, active-message refreshes, and outcome notifications.
Messages are acknowledged only after their handler completes successfully.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
from dataclasses import dataclass
from typing import Any, Mapping

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _delivery_redis_url() -> str:
    return str(os.getenv("DELIVERY_REDIS_URL") or "").strip()


@dataclass(frozen=True, slots=True)
class StreamMessage:
    message_id: str
    payload: dict[str, Any]
    enqueued_at_ms: int
    attempts: int = 0

    @property
    def age_ms(self) -> int:
        return max(0, int(time.time() * 1000) - int(self.enqueued_at_ms or 0))


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    accepted: bool
    duplicate: bool = False
    message_id: str | None = None
    reason: str = ""


class RecoverableStream:
    """One capped consumer-group stream with retry and dead-letter semantics."""

    def __init__(
        self,
        *,
        name: str,
        group: str,
        dead_letter_name: str | None = None,
        redis_url: str | None = None,
        max_length: int | None = None,
        max_attempts: int | None = None,
        claim_idle_ms: int | None = None,
        dedupe_ttl_seconds: int | None = None,
    ) -> None:
        self.name = str(name)
        self.group = str(group)
        self.dead_letter_name = str(dead_letter_name or f"{name}:dead_letter")
        self.redis_url = str(redis_url or _delivery_redis_url()).strip()
        self.max_length = max_length or _env_int(
            "DELIVERY_STREAM_MAX_LENGTH", 10_000, minimum=100, maximum=1_000_000
        )
        self.max_attempts = max_attempts or _env_int(
            "DELIVERY_STREAM_MAX_ATTEMPTS", 5, minimum=1, maximum=100
        )
        self.claim_idle_ms = claim_idle_ms or _env_int(
            "DELIVERY_STREAM_CLAIM_IDLE_MS", 60_000, minimum=1_000, maximum=86_400_000
        )
        self.dedupe_ttl_seconds = dedupe_ttl_seconds or _env_int(
            "DELIVERY_STREAM_DEDUPE_TTL_SECONDS",
            7 * 24 * 3600,
            minimum=60,
            maximum=30 * 24 * 3600,
        )
        self._client: Any | None = None
        self._group_ready = False
        self._group_lock = asyncio.Lock()
        self._attempts_key = f"{self.name}:attempts"
        self._dedupe_prefix = f"{self.name}:dedupe:"

    @property
    def configured(self) -> bool:
        return bool(self.redis_url)

    async def _get_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        if not self.configured:
            return None
        from redis.asyncio import Redis

        self._client = Redis.from_url(
            self.redis_url,
            decode_responses=True,
            socket_connect_timeout=0.75,
            socket_timeout=1.5,
            health_check_interval=30,
            max_connections=_env_int(
                "REDIS_MAX_CONNECTIONS", 24, minimum=2, maximum=64
            ),
            retry_on_timeout=True,
        )
        return self._client

    async def ping(self) -> bool:
        client = await self._get_client()
        if client is None:
            return False
        try:
            return bool(await asyncio.wait_for(client.ping(), timeout=1.0))
        except Exception:
            return False

    async def ensure_group(self) -> bool:
        if self._group_ready:
            return True
        async with self._group_lock:
            if self._group_ready:
                return True
            client = await self._get_client()
            if client is None:
                return False
            try:
                await client.xgroup_create(
                    name=self.name,
                    groupname=self.group,
                    id="0-0",
                    mkstream=True,
                )
            except Exception as exc:
                if "BUSYGROUP" not in str(exc).upper():
                    raise
            self._group_ready = True
            return True

    async def enqueue(
        self,
        payload: Mapping[str, Any],
        *,
        idempotency_key: str,
    ) -> EnqueueResult:
        client = await self._get_client()
        if client is None:
            return EnqueueResult(False, reason="delivery_redis_not_configured")
        await self.ensure_group()

        key = str(idempotency_key or "").strip()
        if not key:
            return EnqueueResult(False, reason="idempotency_key_required")
        dedupe_key = f"{self._dedupe_prefix}{key}"
        reserved = await client.set(
            dedupe_key,
            "1",
            ex=self.dedupe_ttl_seconds,
            nx=True,
        )
        if not reserved:
            return EnqueueResult(True, duplicate=True, reason="duplicate")

        try:
            depth = int(await client.xlen(self.name))
            if depth >= self.max_length:
                await client.delete(dedupe_key)
                return EnqueueResult(False, reason="backpressure")
            now_ms = int(time.time() * 1000)
            message_id = await client.xadd(
                self.name,
                {
                    "payload": json.dumps(
                        dict(payload),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "idempotency_key": key,
                    "enqueued_at_ms": str(now_ms),
                },
                maxlen=self.max_length,
                approximate=True,
            )
            return EnqueueResult(True, message_id=str(message_id))
        except Exception:
            try:
                await client.delete(dedupe_key)
            except Exception:
                logger.debug("[redis_stream] failed to release enqueue reservation", exc_info=True)
            raise

    async def _attempts(self, client: Any, message_id: str) -> int:
        try:
            return int(await client.hget(self._attempts_key, message_id) or 0)
        except Exception:
            return 0

    async def _decode(
        self,
        client: Any,
        message_id: Any,
        fields: Mapping[str, Any],
    ) -> StreamMessage | None:
        try:
            payload = json.loads(str(fields.get("payload") or "{}"))
            if not isinstance(payload, dict):
                raise TypeError("payload must be an object")
            enqueued_at_ms = int(fields.get("enqueued_at_ms") or 0)
            message_id_s = str(message_id)
            return StreamMessage(
                message_id=message_id_s,
                payload=payload,
                enqueued_at_ms=enqueued_at_ms,
                attempts=await self._attempts(client, message_id_s),
            )
        except Exception as exc:
            logger.warning(
                "[redis_stream] invalid message stream=%s id=%s error=%s",
                self.name,
                message_id,
                type(exc).__name__,
            )
            await self._dead_letter_raw(
                client,
                str(message_id),
                fields,
                reason="invalid_payload",
            )
            await client.xack(self.name, self.group, str(message_id))
            return None

    async def _claim_stale(
        self,
        client: Any,
        *,
        consumer: str,
        count: int,
    ) -> list[tuple[Any, Mapping[str, Any]]]:
        try:
            claimed = await client.xautoclaim(
                self.name,
                self.group,
                consumer,
                min_idle_time=self.claim_idle_ms,
                start_id="0-0",
                count=count,
            )
        except Exception as exc:
            if "unknown command" in str(exc).lower():
                return []
            raise
        if not claimed:
            return []
        # redis-py versions return (next_id, messages) or
        # (next_id, messages, deleted_ids).
        messages = claimed[1] if len(claimed) >= 2 else []
        return list(messages or [])

    async def read(
        self,
        *,
        consumer: str,
        count: int = 1,
        block_ms: int = 1_000,
    ) -> list[StreamMessage]:
        client = await self._get_client()
        if client is None or not await self.ensure_group():
            return []
        wanted = max(1, min(100, int(count)))
        raw_messages = await self._claim_stale(
            client,
            consumer=consumer,
            count=wanted,
        )
        if not raw_messages:
            rows = await client.xreadgroup(
                groupname=self.group,
                consumername=consumer,
                streams={self.name: ">"},
                count=wanted,
                block=max(0, min(60_000, int(block_ms))),
            )
            raw_messages = []
            for _stream_name, messages in rows or []:
                raw_messages.extend(messages or [])

        decoded: list[StreamMessage] = []
        for message_id, fields in raw_messages:
            message = await self._decode(client, message_id, fields)
            if message is not None:
                decoded.append(message)
        return decoded

    async def ack(self, message_id: str) -> bool:
        client = await self._get_client()
        if client is None:
            return False
        acknowledged = int(await client.xack(self.name, self.group, message_id))
        await client.hdel(self._attempts_key, message_id)
        return acknowledged > 0

    async def _dead_letter_raw(
        self,
        client: Any,
        message_id: str,
        fields: Mapping[str, Any],
        *,
        reason: str,
        attempts: int | None = None,
    ) -> None:
        await client.xadd(
            self.dead_letter_name,
            {
                "source_stream": self.name,
                "source_message_id": str(message_id),
                "payload": str(fields.get("payload") or "{}"),
                "idempotency_key": str(fields.get("idempotency_key") or ""),
                "enqueued_at_ms": str(fields.get("enqueued_at_ms") or "0"),
                "dead_lettered_at_ms": str(int(time.time() * 1000)),
                "attempts": str(attempts or 0),
                "reason": str(reason)[:512],
            },
            maxlen=self.max_length,
            approximate=True,
        )

    async def fail(self, message: StreamMessage, error: BaseException | str) -> int:
        """Record failure; dead-letter and acknowledge only at the retry limit."""
        client = await self._get_client()
        if client is None:
            return message.attempts
        attempts = int(await client.hincrby(self._attempts_key, message.message_id, 1))
        await client.expire(
            self._attempts_key,
            max(self.dedupe_ttl_seconds, 24 * 3600),
        )
        if attempts < self.max_attempts:
            return attempts
        rows = await client.xrange(
            self.name,
            min=message.message_id,
            max=message.message_id,
            count=1,
        )
        fields = rows[0][1] if rows else {
            "payload": json.dumps(message.payload, separators=(",", ":")),
            "enqueued_at_ms": str(message.enqueued_at_ms),
        }
        await self._dead_letter_raw(
            client,
            message.message_id,
            fields,
            reason=f"{type(error).__name__}: {str(error)[:400]}",
            attempts=attempts,
        )
        await client.xack(self.name, self.group, message.message_id)
        await client.hdel(self._attempts_key, message.message_id)
        return attempts

    async def metrics(self) -> dict[str, int]:
        client = await self._get_client()
        if client is None:
            return {"depth": 0, "pending": 0, "dead_letter_depth": 0}
        await self.ensure_group()
        pending = await client.xpending(self.name, self.group)
        pending_count = int(
            pending.get("pending", 0)
            if isinstance(pending, dict)
            else (pending[0] if pending else 0)
        )
        return {
            "depth": int(await client.xlen(self.name)),
            "pending": pending_count,
            "dead_letter_depth": int(await client.xlen(self.dead_letter_name)),
        }

    async def close(self) -> None:
        client, self._client = self._client, None
        self._group_ready = False
        if client is None:
            return
        close = getattr(client, "aclose", None) or getattr(client, "close", None)
        if close is not None:
            result = close()
            if asyncio.iscoroutine(result):
                await result


_TELEGRAM_STREAM: RecoverableStream | None = None


def telegram_update_stream() -> RecoverableStream:
    global _TELEGRAM_STREAM
    url = _delivery_redis_url()
    if _TELEGRAM_STREAM is None or _TELEGRAM_STREAM.redis_url != url:
        _TELEGRAM_STREAM = RecoverableStream(
            name=str(
                os.getenv("TELEGRAM_UPDATES_STREAM")
                or "signalrank:telegram_updates:v1"
            ),
            group=str(
                os.getenv("TELEGRAM_UPDATES_CONSUMER_GROUP")
                or "signalrank:telegram"
            ),
            dead_letter_name=str(
                os.getenv("TELEGRAM_UPDATES_DLQ_STREAM")
                or "signalrank:telegram_updates:dead_letter:v1"
            ),
            redis_url=url,
        )
    return _TELEGRAM_STREAM


def stream_consumer_name(prefix: str = "consumer") -> str:
    host = socket.gethostname().replace(":", "_")[:48] or "unknown"
    return f"{prefix}:{host}:{os.getpid()}"


__all__ = [
    "EnqueueResult",
    "RecoverableStream",
    "StreamMessage",
    "stream_consumer_name",
    "telegram_update_stream",
]
