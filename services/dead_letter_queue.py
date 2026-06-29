"""
Dead Letter Queue (DLQ) for SignalRankAI.

This module handles persistently failed deliveries that need manual intervention
or retry after system recovery.

Features:
- Track failed deliveries with full context
- Retry with configurable intervals
- Alert on DLQ growth
- Manual reprocess support

Usage:
    dlq = DeadLetterQueue()
    
    # Add a failed delivery
    await dlq.add(signal_id, user_id, error, payload)
    
    # Process pending retries
    await dlq.process_pending()
    
    # Get DLQ status
    count = await dlq.get_count()
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Configuration
MAX_DLQ_RETRIES = int(os.getenv("DLQ_MAX_RETRIES", "10"))
RETRY_INTERVAL_HOURS = int(os.getenv("DLQ_RETRY_INTERVAL_HOURS", "1"))
DLQ_ALERT_THRESHOLD = int(os.getenv("DLQ_ALERT_THRESHOLD", "100"))


class DeadLetterQueue:
    """
    Dead Letter Queue for persistently failed deliveries.
    
    When a signal delivery fails repeatedly, it's moved here instead of
    filling up the retry queue. These are retried periodically or
    can be manually reprocessed after fixing the issue.
    """
    
    def __init__(self):
        self._redis = None
        self._redis_url = self._resolve_redis_url()
        
        if self._redis_url:
            self._init_redis()
    
    def _resolve_redis_url(self) -> Optional[str]:
        return os.getenv("REDIS_URL") or os.getenv("REDIS_PRIVATE_URL") or None
    
    def _init_redis(self):
        try:
            import redis
            self._redis = redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            self._redis.ping()
            logger.info("[dlq] Connected to Redis")
        except Exception as e:
            logger.debug(f"[dlq] Redis unavailable: {e}")
            self._redis = None
    
    async def add(
        self,
        signal_id: str,
        user_id: int,
        error: str,
        payload: Dict[str, Any],
        retry_at: Optional[datetime] = None
    ) -> str:
        """
        Add a failed delivery to the DLQ.
        
        Args:
            signal_id: Signal ID
            user_id: User ID who didn't receive
            error: Error message
            payload: Full signal payload
            retry_at: When to retry (default: now + 1 hour)
            
        Returns:
            DLQ entry ID
        """
        import json
        
        if retry_at is None:
            retry_at = datetime.utcnow() + timedelta(hours=RETRY_INTERVAL_HOURS)
        
        entry_id = f"dlq:{signal_id}:{user_id}:{int(datetime.utcnow().timestamp())}"
        
        entry = {
            "signal_id": signal_id,
            "user_id": user_id,
            "error": error,
            "payload": payload,
            "retry_at": retry_at.isoformat(),
            "created_at": datetime.utcnow().isoformat(),
            "retry_count": 0,
        }
        
        # Store in Redis
        if self._redis:
            self._redis.hset(
                "signalrankai:dlq",
                entry_id,
                json.dumps(entry)
            )
            self._redis.zadd(
                "signalrankai:dlq:ready",
                {entry_id: retry_at.timestamp()}
            )
        
        # Also store in DB for persistence
        try:
            from db.session import get_session
            from db.models import RuntimeState
            
            async with get_session() as session:
                state = RuntimeState(
                    key=f"dlq:{entry_id}",
                    value=entry
                )
                session.add(state)
                await session.commit()
        except Exception:
            pass
        
        logger.warning(f"[dlq] Added {entry_id}: {error}")
        
        # Check for alert threshold
        await self._check_alert_threshold()
        
        return entry_id
    
    async def get_pending(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get entries ready for retry."""
        import json
        
        entries = []
        now = datetime.utcnow().timestamp()
        
        # Get from Redis
        if self._redis:
            ready_ids = self._redis.zrangebyscore(
                "signalrankai:dlq:ready",
                0,
                now,
                start=0,
                num=limit
            )
            
            for entry_id in (ready_ids or []):
                data = self._redis.hget("signalrankai:dlq", entry_id)
                if data:
                    try:
                        entry = json.loads(data)
                        entry["entry_id"] = entry_id
                        entries.append(entry)
                    except Exception:
                        pass
        
        return entries
    
    async def mark_processed(self, entry_id: str) -> None:
        """Mark a DLQ entry as successfully processed."""
        import json
        
        if self._redis:
            # Remove from ready queue
            self._redis.zrem("signalrankai:dlq:ready", entry_id)
            self._redis.hdel("signalrankai:dlq", entry_id)
        
        # Remove from DB
        try:
            from db.session import get_session
            from db.models import RuntimeState
            
            async with get_session() as session:
                from sqlalchemy import delete
                await session.execute(
                    delete(RuntimeState).where(
                        RuntimeState.key.like(f"dlq:{entry_id}%")
                    )
                )
                await session.commit()
        except Exception:
            pass
        
        logger.info(f"[dlq] Processed and removed {entry_id}")
    
    async def retry(self, entry_id: str) -> bool:
        """Retry a DLQ entry."""
        import json
        
        # Get entry
        data = None
        
        if self._redis:
            data = self._redis.hget("signalrankai:dlq", entry_id)
        
        if not data:
            return False
        
        try:
            entry = json.loads(data)
            payload = entry.get("payload", {})
            user_id = entry.get("user_id")
            
            # Try to deliver again
            from signalrank_telegram.bot import dispatch_signals_async
            
            await dispatch_signals_async([payload], user_id=user_id)
            
            # Success - mark as processed
            await self.mark_processed(entry_id)
            
            logger.info(f"[dlq] Retry succeeded for {entry_id}")
            return True
            
        except Exception as e:
            # Increment retry count
            entry["retry_count"] = entry.get("retry_count", 0) + 1
            entry["last_error"] = str(e)
            
            if entry["retry_count"] >= MAX_DLQ_RETRIES:
                # Too many retries - keep but don't retry automatically
                logger.warning(f"[dlq] Max retries reached for {entry_id}, will require manual intervention")
            else:
                # Schedule next retry
                next_retry = datetime.utcnow() + timedelta(hours=RETRY_INTERVAL_HOURS)
                entry["retry_at"] = next_retry.isoformat()
                
                # Update in Redis
                if self._redis:
                    self._redis.hset(
                        "signalrankai:dlq",
                        entry_id,
                        json.dumps(entry)
                    )
                    self._redis.zadd(
                        "signalrankai:dlq:ready",
                        {entry_id: next_retry.timestamp()}
                    )
            
            logger.debug(f"[dlq] Retry failed for {entry_id}: {e}")
            return False
    
    async def process_pending(self, limit: int = 50) -> Dict[str, int]:
        """Process all pending DLQ entries."""
        pending = await self.get_pending(limit=limit)
        
        stats = {
            "attempted": 0,
            "succeeded": 0,
            "failed": 0,
        }
        
        for entry in pending:
            stats["attempted"] += 1
            entry_id = entry.get("entry_id")
            
            if await self.retry(entry_id):
                stats["succeeded"] += 1
            else:
                stats["failed"] += 1
        
        logger.info(f"[dlq] Processed {stats['attempted']} entries: {stats['succeeded']} succeeded, {stats['failed']} failed")
        
        return stats
    
    async def get_count(self) -> int:
        """Get total number of entries in DLQ."""
        if self._redis:
            return self._redis.zcard("signalrankai:dlq:ready")
        return 0
    
    async def get_all_entries(self) -> List[Dict[str, Any]]:
        """Get all DLQ entries (not just pending)."""
        import json
        
        entries = []
        
        if self._redis:
            all_data = self._redis.hgetall("signalrankai:dlq")
            for entry_id, data in (all_data or {}).items():
                try:
                    entry = json.loads(data)
                    entry["entry_id"] = entry_id
                    entries.append(entry)
                except Exception:
                    pass
        
        return entries
    
    async def _check_alert_threshold(self) -> None:
        """Alert admins if DLQ grows too large."""
        count = await self.get_count()
        
        if count >= DLQ_ALERT_THRESHOLD:
            try:
                from config import ADMIN_IDS
                import os
                
                bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
                if not bot_token:
                    return
                
                import requests
                message = f"🚨 DLQ Alert: {count} failed deliveries need attention"
                
                for admin_id in (ADMIN_IDS or []):
                    try:
                        requests.post(
                            f"https://api.telegram.org/bot{bot_token}/sendMessage",
                            json={"chat_id": admin_id, "text": message},
                            timeout=10,
                        )
                    except Exception:
                        pass
            except Exception:
                pass
    
    async def manual_reprocess(self, entry_id: str) -> bool:
        """Manually reprocess a specific DLQ entry."""
        return await self.retry(entry_id)
    
    async def remove(self, entry_id: str) -> None:
        """Manually remove a DLQ entry without retry."""
        await self.mark_processed(entry_id)


# Global DLQ instance
_dlq: Optional[DeadLetterQueue] = None


def get_dead_letter_queue() -> DeadLetterQueue:
    """Get or create the global DLQ."""
    global _dlq
    if _dlq is None:
        _dlq = DeadLetterQueue()
    return _dlq
