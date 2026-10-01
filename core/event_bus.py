"""
Redis-backed Event Bus for SignalRankAI.

Implements an event-driven architecture where:
- Engine publishes SIGNAL_READY events when signals are generated
- Broadcaster subscribes and delivers to users in parallel
- Workers process trade outcomes and ML feedback

This ensures instant delivery and decouples signal generation from delivery.
"""

from utils.timeutils import now_utc_naive

import os
import json
import asyncio
import logging
from collections import deque
import time
from typing import Any, Dict, List, Optional, Callable, Awaitable
from uuid import uuid4

from core.event_types import SIGNAL_READY, SIGNAL_DELIVERED, SIGNAL_FAILED, CHANNEL_SIGNALS, EVENT_PRIORITIES

logger = logging.getLogger(__name__)

# Redis key prefix
_EVENT_PREFIX = "signalrankai:events:"


def _resolve_redis_url() -> Optional[str]:
    """Get Redis URL from environment."""
    return os.getenv("REDIS_URL") or os.getenv("REDIS_PRIVATE_URL") or None


class EventBus:
    """
    Redis-backed event bus for cross-process communication.

    Features:
    - Pub/Sub for real-time events
    - Stream-based for durability
    - Dead letter queue for failed processing

    Usage:
        # Publish a signal ready event
        await event_bus.publish(SIGNAL_READY, signal_data, priority=90)

        # Subscribe to signals
        async for event in event_bus.subscribe(CHANNEL_SIGNALS):
            await process_signal(event)
    """

    def __init__(self):
        self._redis = None
        self._redis_url = _resolve_redis_url()
        self._pubsub = None
        self._has_redis = False
        self._subscriptions: Dict[str, Callable] = {}
        self._running = False

        # Memory fallback is bounded and restricted to local/test environments.
        # Production/staging must fail closed if the durable Redis transport is
        # unavailable rather than silently accepting lossy critical events.
        env_name = str(os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "").strip().lower()
        explicit_fallback = str(os.getenv("EVENT_BUS_MEMORY_FALLBACK_ENABLED") or "").strip().lower()
        self._memory_fallback_allowed = (
            explicit_fallback in {"1", "true", "yes", "on"}
            or env_name in {"", "local", "dev", "development", "test", "testing"}
        )
        outbox_raw = str(os.getenv("EVENT_BUS_DB_OUTBOX_ENABLED") or "1").strip().lower()
        self._db_outbox_enabled = (
            outbox_raw in {"1", "true", "yes", "on"}
            and env_name not in {"local", "dev", "development", "test", "testing"}
        )
        fallback_limit = max(1, min(10000, int(os.getenv("EVENT_BUS_MEMORY_FALLBACK_MAXLEN", "1000") or 1000)))
        self._fallback_queue = deque(maxlen=fallback_limit)

        self._init_redis()

    def _init_redis(self) -> None:
        """Initialize Redis connection."""
        if not self._redis_url:
            logger.debug("[event_bus] No REDIS_URL configured, using in-memory fallback")
            return

        try:
            import redis

            self._redis = redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
                max_connections=20,
            )
            # Test connection
            self._redis.ping()
            self._has_redis = True
            logger.info("[event_bus] Connected to Redis for event bus")
        except Exception as e:
            logger.debug(f"[event_bus] Redis unavailable, using in-memory fallback: {e}")
            self._redis = None
            self._has_redis = False

    def _get_redis(self):
        """Get or reconnect Redis client."""
        if self._redis is None:
            self._init_redis()
        return self._redis

    async def _publish_to_redis(self, event: Dict[str, Any], channel: str) -> bool:
        """Publish one already-identified event without invoking fallback logic."""
        client = self._get_redis()
        if client is None or not self._has_redis:
            return False
        try:
            serialized = json.dumps(event, separators=(",", ":"), default=str)
            client.publish(channel, serialized)
            stream_key = f"{_EVENT_PREFIX}stream"
            client.xadd(
                stream_key,
                {
                    "event_id": str(event["id"]),
                    "event_type": str(event["type"]),
                    "priority": str(event["priority"]),
                    "channel": str(channel),
                    "data": json.dumps(event["payload"], separators=(",", ":"), default=str),
                },
                maxlen=10000,
            )
            client.incr(f"{_EVENT_PREFIX}published:{event['type']}")
            return True
        except Exception as exc:
            logger.warning("[event_bus] Redis publish failed type=%s err=%s", event.get("type"), type(exc).__name__)
            self._has_redis = False
            self._redis = None
            return False

    async def _persist_to_outbox(self, event: Dict[str, Any], channel: str) -> bool:
        if not self._db_outbox_enabled:
            return False
        try:
            from core.transactional_outbox import PostgresTransactionalOutbox

            payload = dict(event.get("payload") or {})
            partition_key = str(
                payload.get("signal_id")
                or payload.get("user_id")
                or payload.get("asset")
                or channel
                or event.get("type")
            )
            outbox = PostgresTransactionalOutbox()
            await outbox.enqueue(
                entry_id=str(event["id"]),
                event_type=str(event["type"]),
                partition_key=partition_key,
                payload={
                    "event_id": str(event["id"]),
                    "payload": payload,
                    "priority": int(event.get("priority") or 50),
                    "channel": str(channel),
                },
                idempotency_key=str(event["id"]),
                occurred_at=str(event["timestamp"]),
            )
            logger.warning("[event_bus] persisted event to DB outbox type=%s id=%s", event.get("type"), event.get("id"))
            return True
        except Exception as exc:
            logger.error(
                "[event_bus] DB outbox persistence failed type=%s err=%s",
                event.get("type"),
                type(exc).__name__,
            )
            return False

    async def publish(
        self, event_type: str, payload: Dict[str, Any], priority: Optional[int] = None, channel: str = CHANNEL_SIGNALS
    ) -> bool:
        """Publish with Redis-first delivery and durable PostgreSQL fallback."""
        if priority is None:
            priority = EVENT_PRIORITIES.get(event_type, 50)

        event = {
            "type": event_type,
            "payload": dict(payload),
            "priority": int(priority),
            "timestamp": now_utc_naive().isoformat(),
            "id": str(uuid4()),
        }

        if await self._publish_to_redis(event, channel):
            logger.debug("[event_bus] Published %s with priority %s", event_type, priority)
            return True

        # In production/staging, persist a durable retry record before reporting
        # acceptance. The worker relay publishes it after Redis recovers.
        if await self._persist_to_outbox(event, channel):
            return True

        # Local/test only: bounded non-durable fallback for hermetic tests.
        if not self._memory_fallback_allowed:
            logger.error(
                "[event_bus] no durable transport available; event rejected type=%s channel=%s",
                event_type,
                channel,
            )
            return False
        self._fallback_queue.append(event)
        logger.warning("[event_bus] using bounded non-durable fallback type=%s", event_type)
        return True

    async def subscribe(
        self, channel: str = CHANNEL_SIGNALS, callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
    ) -> "EventSubscriber":
        """
        Create a subscriber for events.

        Args:
            channel: Channel to subscribe to
            callback: Optional async callback to process events

        Returns:
            EventSubscriber object
        """
        return EventSubscriber(self, channel, callback)

    async def get_pending_events(self, event_type: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get pending events from the stream.

        Args:
            event_type: Filter by event type
            limit: Maximum events to return

        Returns:
            List of pending events
        """
        events = []

        if self._has_redis and self._redis:
            try:
                stream_key = f"{_EVENT_PREFIX}stream"

                # Read from stream
                if event_type:
                    events_data = self._redis.xread({stream_key: "0-0"}, count=limit)
                else:
                    events_data = self._redis.xread({stream_key: "0-0"}, count=limit)

                for stream_name, messages in events_data or []:
                    for msg_id, msg in messages:
                        try:
                            event = {
                                "id": msg_id,
                                "type": msg.get("event_type"),
                                "payload": json.loads(msg.get("data", "{}")),
                                "priority": int(msg.get("priority", 50)),
                            }
                            if event_type is None or event["type"] == event_type:
                                events.append(event)
                        except Exception:
                            continue
            except Exception as e:
                logger.debug(f"[event_bus] Failed to read stream: {e}")

        # Also check in-memory fallback
        for event in list(self._fallback_queue)[-limit:]:
            if event_type is None or event.get("type") == event_type:
                events.append(event)

        # Sort by priority (highest first)
        events.sort(key=lambda x: x.get("priority", 0), reverse=True)

        return events[:limit]

    async def acknowledge(self, event_id: str) -> None:
        """Mark an event as processed."""
        if self._has_redis and self._redis:
            try:
                stream_key = f"{_EVENT_PREFIX}stream"
                self._redis.xack(stream_key, "signalrankai_group", event_id)
            except Exception:
                pass

    async def get_stats(self) -> Dict[str, int]:
        """Get event bus statistics."""
        stats = {"pending_in_memory": len(self._fallback_queue), "has_redis": 1 if self._has_redis else 0}

        if self._has_redis and self._redis:
            try:
                for key in self._redis.keys(f"{_EVENT_PREFIX}published:*"):
                    event_type = key.split(":")[-1]
                    stats[event_type] = int(self._redis.get(key) or 0)
            except Exception:
                pass

        if self._db_outbox_enabled:
            try:
                from core.transactional_outbox import PostgresTransactionalOutbox
                stats["pending_db_outbox"] = int(await PostgresTransactionalOutbox().depth())
            except Exception:
                stats["pending_db_outbox"] = -1

        return stats

    def is_healthy(self) -> bool:
        """Check if event bus is operational."""
        return bool(self._has_redis or self._memory_fallback_allowed)


class EventSubscriber:
    """Async iterator for processing events from the event bus."""

    def __init__(
        self, event_bus: EventBus, channel: str, callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
    ):
        self.event_bus = event_bus
        self.channel = channel
        self.callback = callback
        self._running = True

    async def __aiter__(self):
        return self

    async def __anext__(self) -> Dict[str, Any]:
        """Get next event from the bus."""
        if not self._running:
            raise StopAsyncIteration()

        # Try to get from Redis pub/sub
        if self.event_bus._has_redis and self.event_bus._redis:
            try:
                pubsub = self.event_bus._redis.pubsub()
                await pubsub.subscribe(self.channel)

                for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            event = json.loads(message["data"])
                            if self.callback:
                                await self.callback(event)
                            return event
                        except Exception:
                            continue
            except Exception:
                pass

        # Fallback to in-memory queue
        if self.event_bus._fallback_queue:
            event = self.event_bus._fallback_queue.popleft()
            if self.callback:
                await self.callback(event)
            return event

        # Wait a bit and try again
        await asyncio.sleep(0.1)
        return await self.__anext__()

    def stop(self):
        """Stop the subscriber."""
        self._running = False


# Global event bus instance
event_bus = EventBus()


# Convenience functions


async def publish_outbox_entry(entry: Any) -> None:
    """Relay one persisted DB outbox entry back to Redis without recursion."""
    body = dict(getattr(entry, "payload", {}) or {})
    event = {
        "id": str(body.get("event_id") or getattr(entry, "entry_id", "")),
        "type": str(getattr(entry, "event_type", "") or ""),
        "payload": dict(body.get("payload") or {}),
        "priority": int(body.get("priority") or EVENT_PRIORITIES.get(str(getattr(entry, "event_type", "")), 50)),
        "timestamp": str(getattr(entry, "occurred_at", "") or now_utc_naive().isoformat()),
    }
    channel = str(body.get("channel") or CHANNEL_SIGNALS)
    if not await event_bus._publish_to_redis(event, channel):
        raise RuntimeError("event_redis_unavailable")


async def publish_signal_ready(signal: Dict[str, Any], priority: int = 90) -> bool:
    """
    Publish a SIGNAL_READY event when a signal is generated.

    This is the main entry point for the event-driven architecture.
    The broadcaster service listens for these events and delivers to users.
    """
    return await event_bus.publish(SIGNAL_READY, signal, priority=priority)


async def publish_signal_delivered(signal_id: str, user_id: int) -> bool:
    """Publish a SIGNAL_DELIVERED event after successful delivery."""
    return await event_bus.publish(SIGNAL_DELIVERED, {"signal_id": signal_id, "user_id": user_id}, priority=50)


async def publish_signal_failed(signal_id: str, user_id: int, error: str) -> bool:
    """Publish a SIGNAL_FAILED event for retry logic."""
    return await event_bus.publish(
        SIGNAL_FAILED, {"signal_id": signal_id, "user_id": user_id, "error": error}, priority=75
    )


# Backwards compatibility adapter
class EventBusAdapter:
    """Adapter providing backwards-compatible API."""

    @property
    def bus(self) -> EventBus:
        return event_bus

    async def publish_signal(self, signal: Dict[str, Any]) -> bool:
        return await publish_signal_ready(signal)

    async def get_pending(self, limit: int = 100) -> List[Dict[str, Any]]:
        return await event_bus.get_pending_events(limit=limit)


# Legacy compatibility
event_bus_adapter = EventBusAdapter()
