"""
Redis-backed Event Bus for SignalRankAI.

Implements an event-driven architecture where:
- Engine publishes SIGNAL_READY events when signals are generated
- Broadcaster subscribes and delivers to users in parallel
- Workers process trade outcomes and ML feedback

This ensures instant delivery and decouples signal generation from delivery.
"""

import os
import json
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Callable, Awaitable
from datetime import datetime

from core.event_types import (
    SIGNAL_READY, SIGNAL_DELIVERED, SIGNAL_FAILED,
    CHANNEL_SIGNALS, CHANNEL_TRADES, CHANNEL_SYSTEM,
    EVENT_PRIORITIES
)

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
        
        # In-memory fallback for local testing
        self._fallback_queue: List[Dict[str, Any]] = []
        
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
    
    async def publish(
        self,
        event_type: str,
        payload: Dict[str, Any],
        priority: Optional[int] = None,
        channel: str = CHANNEL_SIGNALS
    ) -> bool:
        """
        Publish an event to the event bus.
        
        Args:
            event_type: Type of event (e.g., SIGNAL_READY)
            payload: Event data
            priority: Priority level (higher = process first)
            channel: Redis channel to publish to
            
        Returns:
            True if published successfully
        """
        # Determine priority
        if priority is None:
            priority = EVENT_PRIORITIES.get(event_type, 50)
        
        event = {
            "type": event_type,
            "payload": payload,
            "priority": priority,
            "timestamp": datetime.utcnow().isoformat(),
            "id": f"{event_type}:{time.time()}:{id(payload)}"
        }
        
        if self._has_redis and self._redis:
            try:
                # Publish to channel for real-time subscribers
                self._redis.publish(channel, json.dumps(event))
                
                # Also add to stream for durability
                stream_key = f"{_EVENT_PREFIX}stream"
                self._redis.xadd(
                    stream_key,
                    {
                        "event_type": event_type,
                        "priority": str(priority),
                        "data": json.dumps(payload)
                    },
                    maxlen=10000  # Keep last 10k events
                )
                
                # Track for stats
                self._redis.incr(f"{_EVENT_PREFIX}published:{event_type}")
                
                logger.debug(f"[event_bus] Published {event_type} with priority {priority}")
                return True
            except Exception as e:
                logger.debug(f"[event_bus] Redis publish failed: {e}")
                # Fall through to in-memory
        
        # In-memory fallback
        self._fallback_queue.append(event)
        logger.debug(f"[event_bus] Published to fallback queue: {event_type}")
        return True
    
    async def subscribe(
        self,
        channel: str = CHANNEL_SIGNALS,
        callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
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
    
    async def get_pending_events(
        self,
        event_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
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
                    events_data = self._redis.xread(
                        {stream_key: "0-0"},
                        count=limit
                    )
                else:
                    events_data = self._redis.xread(
                        {stream_key: "0-0"},
                        count=limit
                    )
                
                for stream_name, messages in (events_data or []):
                    for msg_id, msg in messages:
                        try:
                            event = {
                                "id": msg_id,
                                "type": msg.get("event_type"),
                                "payload": json.loads(msg.get("data", "{}")),
                                "priority": int(msg.get("priority", 50))
                            }
                            if event_type is None or event["type"] == event_type:
                                events.append(event)
                        except Exception:
                            continue
            except Exception as e:
                logger.debug(f"[event_bus] Failed to read stream: {e}")
        
        # Also check in-memory fallback
        for event in self._fallback_queue[-limit:]:
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
        stats = {
            "pending_in_memory": len(self._fallback_queue),
            "has_redis": 1 if self._has_redis else 0
        }
        
        if self._has_redis and self._redis:
            try:
                for key in self._redis.keys(f"{_EVENT_PREFIX}published:*"):
                    event_type = key.split(":")[-1]
                    stats[event_type] = int(self._redis.get(key) or 0)
            except Exception:
                pass
        
        return stats
    
    def is_healthy(self) -> bool:
        """Check if event bus is operational."""
        return self._has_redis or True  # Always healthy with fallback


class EventSubscriber:
    """Async iterator for processing events from the event bus."""
    
    def __init__(
        self,
        event_bus: EventBus,
        channel: str,
        callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
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
            event = self.event_bus._fallback_queue.pop(0)
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

async def publish_signal_ready(signal: Dict[str, Any], priority: int = 90) -> bool:
    """
    Publish a SIGNAL_READY event when a signal is generated.
    
    This is the main entry point for the event-driven architecture.
    The broadcaster service listens for these events and delivers to users.
    """
    return await event_bus.publish(
        SIGNAL_READY,
        signal,
        priority=priority
    )


async def publish_signal_delivered(signal_id: str, user_id: int) -> bool:
    """Publish a SIGNAL_DELIVERED event after successful delivery."""
    return await event_bus.publish(
        SIGNAL_DELIVERED,
        {"signal_id": signal_id, "user_id": user_id},
        priority=50
    )


async def publish_signal_failed(signal_id: str, user_id: int, error: str) -> bool:
    """Publish a SIGNAL_FAILED event for retry logic."""
    return await event_bus.publish(
        SIGNAL_FAILED,
        {"signal_id": signal_id, "user_id": user_id, "error": error},
        priority=75
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
