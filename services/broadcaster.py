"""
Dedicated Broadcaster Service for SignalRankAI.

This service listens for SIGNAL_READY events from the event bus and delivers
them to users in parallel using asyncio.gather for maximum throughput.

Features:
- Parallel delivery to all eligible users using asyncio.gather
- Automatic retry with exponential backoff for failed deliveries
- Dead Letter Queue for persistent failures
- VIP priority queue for instant delivery
"""

import asyncio
import os
import logging
import time
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from core.event_types import (
    SIGNAL_READY, SIGNAL_DELIVERED, SIGNAL_FAILED,
    PRIORITY_VIP, PRIORITY_HIGH, PRIORITY_NORMAL
)
from core.event_bus import event_bus, publish_signal_delivered, publish_signal_failed

logger = logging.getLogger(__name__)

# Configuration
MAX_PARALLEL_DELIVERIES = int(os.getenv("BROADCASTER_MAX_PARALLEL", "50"))
MAX_RETRIES = int(os.getenv("BROADCASTER_MAX_RETRIES", "3"))
RETRY_BASE_DELAY = float(os.getenv("BROADCASTER_RETRY_DELAY", "1.0"))  # seconds
RETRY_MAX_DELAY = float(os.getenv("BROADCASTER_RETRY_MAX_DELAY", "30.0"))  # seconds


class BroadcasterService:
    """
    Dedicated service for delivering signals to users.
    
    This runs as a separate process/service and listens for SIGNAL_READY
    events from the event bus. When a signal is ready:
    
    1. Fetch all eligible users for the signal
    2. Filter by tier (VIP gets instant delivery)
    3. Send to all users in parallel using asyncio.gather
    4. On failure, add to retry queue with exponential backoff
    5. On persistent failure, move to Dead Letter Queue
    
    Usage:
        broadcaster = BroadcasterService()
        await broadcaster.start()  # Start listening
        await broadcaster.stop()   # Stop and cleanup
    """
    
    def __init__(self):
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._stats = {
            "signals_processed": 0,
            "signals_delivered": 0,
            "signals_failed": 0,
            "retries": 0,
            "dlq_moves": 0,
        }
        self._retry_queue: List[Dict[str, Any]] = []
    
    async def start(self) -> None:
        """Start the broadcaster service."""
        if self._running:
            logger.warning("[broadcaster] Already running")
            return
        
        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        
        logger.info("[broadcaster] Started - listening for SIGNAL_READY events")
    
    async def stop(self) -> None:
        """Stop the broadcaster service."""
        self._running = False
        
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        
        logger.info(f"[broadcaster] Stopped. Stats: {self._stats}")
    
    async def _worker(self) -> None:
        """Main worker loop - processes events from the event bus."""
        while self._running:
            try:
                # Process retry queue first
                await self._process_retry_queue()
                
                # Then check for new signals
                events = await event_bus.get_pending_events(
                    event_type=SIGNAL_READY,
                    limit=50
                )
                
                for event in events:
                    if not self._running:
                        break
                    
                    await self._process_signal_event(event)
                    self._stats["signals_processed"] += 1
                
                # Sleep briefly before checking again
                await asyncio.sleep(0.5)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[broadcaster] Worker error: {e}")
                await asyncio.sleep(1)
    
    async def _process_signal_event(self, event: Dict[str, Any]) -> None:
        """Process a single SIGNAL_READY event."""
        signal = event.get("payload", {})
        priority = event.get("priority", PRIORITY_NORMAL)
        
        if not signal:
            return
        
        signal_id = signal.get("signal_id") or signal.get("id")
        asset = signal.get("asset")
        score = signal.get("score", 0)
        
        logger.info(f"[broadcaster] Processing signal {signal_id} ({asset}) score={score}")
        
        # Get eligible users
        eligible_users = await self._get_eligible_users(signal)
        
        if not eligible_users:
            logger.debug(f"[broadcaster] No eligible users for {signal_id}")
            return
        
        # Deliver in parallel
        await self._deliver_to_users(signal, eligible_users, priority)
    
    async def _get_eligible_users(self, signal: Dict[str, Any]) -> List[int]:
        """Get list of user IDs eligible to receive this signal."""
        try:
            from db.session import get_session
            from db.models import User, SignalDelivery
            from sqlalchemy import select, and_, func
            from signalrank_telegram.access import resolve_user_tier
            from core.tier_constants import TIER_SCORE_THRESHOLDS
            
            score = float(signal.get("score", 0))
            asset = signal.get("asset")
            
            async with get_session() as session:
                # Get all users who haven't received this signal
                # First get users who haven't received this signal
                result = await session.execute(
                    select(User.id, User.tier).where(
                        User.accepted_terms == True
                    )
                )
                all_users = result.fetchall()
                
                eligible = []
                for user_id, tier in all_users:
                    try:
                        # Check tier threshold
                        threshold = TIER_SCORE_THRESHOLDS.get(tier.lower(), 70)
                        if score < threshold:
                            continue
                        
                        # Check if already received
                        if signal_id := signal.get("signal_id"):
                            existing = await session.execute(
                                select(SignalDelivery.id).where(
                                    and_(
                                        SignalDelivery.user_id == user_id,
                                        SignalDelivery.signal_id == signal_id
                                    )
                                )
                            )
                            if existing.first():
                                continue
                        
                        # Check daily limit
                        from db.pg_features import count_signals_sent_today
                        sent_today = await count_signals_sent_today(session, user_id)
                        
                        from core.tier_constants import TIER_DAILY_LIMITS
                        daily_limit = TIER_DAILY_LIMITS.get(tier.lower(), 3)
                        
                        if sent_today < daily_limit:
                            eligible.append(user_id)
                            
                    except Exception:
                        continue
                
                return eligible
                
        except Exception as e:
            logger.error(f"[broadcaster] Failed to get eligible users: {e}")
            return []
    
    async def _deliver_to_users(
        self,
        signal: Dict[str, Any],
        user_ids: List[int],
        priority: int
    ) -> None:
        """Deliver a signal to multiple users in parallel."""
        
        # For VIP priority signals, use smaller batches for faster delivery
        if priority >= PRIORITY_VIP:
            batch_size = min(10, len(user_ids))
        elif priority >= PRIORITY_HIGH:
            batch_size = min(20, len(user_ids))
        else:
            batch_size = min(MAX_PARALLEL_DELIVERIES, len(user_ids))
        
        # Create delivery tasks
        async def deliver_to_one(user_id: int) -> tuple[int, bool, Optional[str]]:
            try:
                # Import here to avoid circular imports
                from signalrank_telegram.bot import dispatch_signals_async
                
                result = await dispatch_signals_async([signal], user_id=user_id)
                
                # Publish delivered event
                signal_id = signal.get("signal_id") or signal.get("id")
                if signal_id:
                    await publish_signal_delivered(signal_id, user_id)
                
                self._stats["signals_delivered"] += 1
                return user_id, True, None
                
            except Exception as e:
                error_msg = str(e)
                self._stats["signals_failed"] += 1
                return user_id, False, error_msg
        
        # Process in batches
        for i in range(0, len(user_ids), batch_size):
            batch = user_ids[i:i + batch_size]
            
            # Use asyncio.gather for parallel delivery
            tasks = [deliver_to_one(uid) for uid in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check for failures and queue for retry
            for result in results:
                if isinstance(result, tuple):
                    user_id, success, error = result
                    if not success and error:
                        # Add to retry queue
                        await self._queue_for_retry(signal, user_id, error)
    
    async def _queue_for_retry(
        self,
        signal: Dict[str, Any],
        user_id: int,
        error: str
    ) -> None:
        """Queue a failed delivery for retry with exponential backoff."""
        self._stats["retries"] += 1
        
        retry_entry = {
            "signal": signal,
            "user_id": user_id,
            "error": error,
            "retry_count": 0,
            "next_retry_at": time.time() + RETRY_BASE_DELAY,
        }
        
        self._retry_queue.append(retry_entry)
        
        logger.debug(f"[broadcaster] Queued retry for user {user_id}: {error}")
    
    async def _process_retry_queue(self) -> None:
        """Process pending retries with exponential backoff."""
        if not self._retry_queue:
            return
        
        current_time = time.time()
        still_pending = []
        
        for entry in self._retry_queue:
            if entry["next_retry_at"] > current_time:
                still_pending.append(entry)
                continue
            
            signal = entry["signal"]
            user_id = entry["user_id"]
            retry_count = entry["retry_count"]
            
            # Calculate next delay with exponential backoff
            delay = min(
                RETRY_BASE_DELAY * (2 ** retry_count),
                RETRY_MAX_DELAY
            )
            
            # Retry the delivery
            try:
                from signalrank_telegram.bot import dispatch_signals_async
                
                await dispatch_signals_async([signal], user_id=user_id)
                
                # Success! Publish delivered event
                signal_id = signal.get("signal_id") or signal.get("id")
                if signal_id:
                    await publish_signal_delivered(signal_id, user_id)
                
                self._stats["signals_delivered"] += 1
                logger.info(f"[broadcaster] Retry succeeded for user {user_id}")
                
            except Exception as e:
                # Increment retry count and check max
                entry["retry_count"] += 1
                entry["error"] = str(e)
                
                if entry["retry_count"] >= MAX_RETRIES:
                    # Move to Dead Letter Queue
                    await self._move_to_dlq(signal, user_id, str(e))
                    self._stats["dlq_moves"] += 1
                    logger.warning(f"[broadcaster] Moved to DLQ after {MAX_RETRIES} retries: user {user_id}")
                else:
                    # Schedule next retry
                    entry["next_retry_at"] = current_time + delay
                    still_pending.append(entry)
                    logger.debug(f"[broadcaster] Retry {entry['retry_count']} scheduled for user {user_id}")
        
        self._retry_queue = still_pending
    
    async def _move_to_dlq(
        self,
        signal: Dict[str, Any],
        user_id: int,
        error: str
    ) -> None:
        """Move a persistently failed delivery to the Dead Letter Queue."""
        try:
            from db.session import get_session
            from db.models import RuntimeState
            import json
            
            async with get_session() as session:
                key = f"dlq:{signal.get('signal_id')}:{user_id}"
                state = RuntimeState(
                    key=key,
                    value={
                        "signal": signal,
                        "user_id": user_id,
                        "error": error,
                        "failed_at": datetime.utcnow().isoformat(),
                    }
                )
                session.add(state)
                await session.commit()
            
            # Also publish the failed event
            signal_id = signal.get("signal_id") or signal.get("id")
            if signal_id:
                await publish_signal_failed(signal_id, user_id, error)
                
        except Exception as e:
            logger.error(f"[broadcaster] Failed to move to DLQ: {e}")
    
    def get_stats(self) -> Dict[str, int]:
        """Get broadcaster statistics."""
        return {
            **self._stats,
            "retry_queue_size": len(self._retry_queue),
        }


# Global broadcaster instance
_broadcaster: Optional[BroadcasterService] = None


async def get_broadcaster() -> BroadcasterService:
    """Get or create the global broadcaster instance."""
    global _broadcaster
    if _broadcaster is None:
        _broadcaster = BroadcasterService()
    return _broadcaster


async def start_broadcaster() -> None:
    """Start the broadcaster service."""
    broadcaster = await get_broadcaster()
    await broadcaster.start()


async def stop_broadcaster() -> None:
    """Stop the broadcaster service."""
    if _broadcaster:
        await _broadcaster.stop()


# Standalone entry point for running as a service
async def run_broadcaster_service():
    """Run the broadcaster as a standalone service."""
    logger.info("[broadcaster] Starting broadcaster service...")
    
    broadcaster = await get_broadcaster()
    await broadcaster.start()
    
    try:
        # Keep running
        while True:
            await asyncio.sleep(60)
            stats = broadcaster.get_stats()
            logger.info(f"[broadcaster] Stats: {stats}")
    except asyncio.CancelledError:
        pass
    finally:
        await broadcaster.stop()


if __name__ == "__main__":
    # Run as standalone service
    asyncio.run(run_broadcaster_service())
