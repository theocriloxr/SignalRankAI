"""
News Sync Worker - Background task to sync economic events to database.

This worker fetches economic calendar data from Finnhub and other sources,
then stores them in the economic_events table for the news filter to use.

Runs every 6 hours (configurable) to keep the calendar up-to-date.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
import os

logger = logging.getLogger("news_sync_worker")

# Import from existing services
try:
    from services.economic_calendar import fetch_economic_calendar, get_upcoming_high_impact_events
except ImportError:
    async def fetch_economic_calendar(days_ahead: int = 7) -> List[Dict[str, Any]]:
        """Fallback when economic_calendar not available."""
        return []
    
    async def get_upcoming_high_impact_events(hours: int = 24) -> List[Dict[str, Any]]:
        """Fallback when economic_calendar not available."""
        return []

# Import for database operations
try:
    from db.session import get_session, is_db_configured
    from db.models import EconomicEvent
    from sqlalchemy import select, delete
    from utils.timeutils import now_utc_naive
except ImportError:
    async def get_session():
        """Fallback - yield None session."""
        yield None
    
    def is_db_configured() -> bool:
        return False
    
    class EconomicEvent:
        pass
    
    def now_utc_naive():
        return datetime.now(timezone.utc)


# Configuration
SYNC_INTERVAL_HOURS = int(os.getenv("NEWS_SYNC_INTERVAL_HOURS", "6"))
MAX_EVENTS_PER_SYNC = int(os.getenv("NEWS_MAX_EVENTS_PER_SYNC", "50"))
ENABLE_NEWS_SYNC = os.getenv("ENABLE_NEWS_SYNC", "1") == "1"


async def sync_economic_events_to_db() -> Dict[str, Any]:
    """
    Fetch economic events from external APIs and store in database.
    
    Returns:
        Dict with 'synced', 'skipped', 'failed' counts and any errors.
    """
    if not ENABLE_NEWS_SYNC:
        logger.info("[news_sync] Disabled by ENABLE_NEWS_SYNC=0")
        return {"status": "disabled", "synced": 0, "skipped": 0, "failed": 0}
    
    if not is_db_configured():
        logger.warning("[news_sync] Database not configured, skipping sync")
        return {"status": "no_db", "synced": 0, "skipped": 0, "failed": 0}
    
    result = {
        "status": "success",
        "synced": 0,
        "skipped": 0,
        "failed": 0,
        "errors": []
    }
    
    try:
        # Fetch economic calendar for next 7 days
        logger.info("[news_sync] Fetching economic calendar...")
        events = await fetch_economic_calendar(days_ahead=7)
        
        if not events:
            logger.info("[news_sync] No events fetched from API")
            result["skipped"] = 0
            return result
        
        logger.info(f"[news_sync] Fetched {len(events)} events from API")
        
        # Process and store events
        async with get_session() as session:
            if session is None:
                logger.warning("[news_sync] Could not get DB session")
                result["status"] = "no_session"
                return result
            
            # Delete old events (older than 2 days) to keep table clean
            cutoff = datetime.now(timezone.utc) - timedelta(days=2)
            try:
                await session.execute(
                    delete(EconomicEvent).where(
                        EconomicEvent.event_date < cutoff
                    )
                )
                await session.commit()
                logger.info("[news_sync] Cleaned up old events")
            except Exception as e:
                logger.warning("[news_sync] Cleanup failed: %s", e)
                await session.rollback()
            
            # Insert new events
            synced = 0
            failed = 0
            
            for event_data in events[:MAX_EVENTS_PER_SYNC]:
                try:
                    # Parse event data
                    event_date = event_data.get("event_date") or event_data.get("datetime")
                    if isinstance(event_date, str):
                        try:
                            event_date = datetime.fromisoformat(event_date.replace('Z', '+00:00'))
                        except:
                            try:
                                event_date = datetime.strptime(event_date, "%Y-%m-%d %H:%M:%S")
                            except:
                                event_date = None
                    
                    if event_date is None:
                        continue
                    
                    # Ensure timezone-aware
                    if event_date.tzinfo is None:
                        event_date = event_date.replace(tzinfo=timezone.utc)
                    
                    currency = event_data.get("currency", "USD")[:8]
                    title = event_data.get("title", "")[:256]
                    impact = event_data.get("impact", "low")[:8]
                    source = event_data.get("source", "finnhub")[:64]
                    
                    # Don't store low-impact events to reduce noise
                    if impact.lower() not in ["high", "medium", "low"]:
                        impact = "low"
                    
                    # Check if event already exists (by title + date + currency)
                    existing = await session.execute(
                        select(EconomicEvent).where(
                            EconomicEvent.title == title,
                            EconomicEvent.event_date == event_date,
                            EconomicEvent.currency == currency
                        )
                    )
                    existing_event = existing.scalar_one_or_none()
                    
                    if existing_event:
                        result["skipped"] += 1
                        continue
                    
                    # Create new event
                    new_event = EconomicEvent(
                        event_date=event_date,
                        currency=currency,
                        title=title,
                        impact=impact,
                        source=source,
                        fetched_at=now_utc_naive()
                    )
                    session.add(new_event)
                    synced += 1
                    
                except Exception as e:
                    logger.warning("[news_sync] Failed to process event: %s", e)
                    failed += 1
                    result["errors"].append(str(e))
                    continue
            
            # Commit all changes
            try:
                await session.commit()
                result["synced"] = synced
                result["failed"] = failed
                logger.info(f"[news_sync] Synced {synced} events, {failed} failed")
            except Exception as e:
                logger.error("[news_sync] Commit failed: %s", e)
                await session.rollback()
                result["failed"] = failed + 1
                result["errors"].append(str(e))
    
    except Exception as e:
        logger.error("[news_sync] Sync failed: %s", e)
        result["status"] = "error"
        result["errors"].append(str(e))
    
    return result


async def get_cached_high_impact_events(hours: int = 24) -> List[Dict[str, Any]]:
    """
    Get high-impact events from database cache (for news filter to use).
    
    This is faster than calling the external API every time.
    """
    if not is_db_configured():
        return []
    
    try:
        async with get_session() as session:
            if session is None:
                return []
            
            from datetime import timedelta
            from sqlalchemy import select, and_
            
            # Get events in the next X hours
            now = datetime.now(timezone.utc)
            window_end = now + timedelta(hours=hours)
            
            result = await session.execute(
                select(EconomicEvent).where(
                    and_(
                        EconomicEvent.event_date >= now,
                        EconomicEvent.event_date <= window_end,
                        EconomicEvent.impact.in_(["high", "medium"])
                    )
                ).order_by(EconomicEvent.event_date)
            )
            
            events = result.scalars().all()
            
            return [
                {
                    "event_date": e.event_date,
                    "currency": e.currency,
                    "title": e.title,
                    "impact": e.impact,
                    "source": e.source
                }
                for e in events
            ]
    except Exception as e:
        logger.warning("[news_sync] Failed to get cached events: %s", e)
        return []


async def run_news_sync_job() -> Dict[str, Any]:
    """
    Main job function - called by scheduler.
    
    This is the entry point for the scheduled task.
    """
    logger.info("[news_sync] Starting scheduled news sync...")
    result = await sync_economic_events_to_db()
    logger.info(
        f"[news_sync] Completed: status={result['status']}, "
        f"synced={result['synced']}, failed={result['failed']}"
    )
    return result


async def start_news_sync_worker():
    """
    Start the news sync worker as a background task.
    
    This runs continuously, syncing every X hours.
    """
    logger.info(f"[news_sync] Starting news sync worker (interval={SYNC_INTERVAL_HOURS}h)...")
    
    # Initial sync on startup
    logger.info("[news_sync] Running initial sync...")
    await sync_economic_events_to_db()
    
    # Periodic sync
    while True:
        try:
            await asyncio.sleep(SYNC_INTERVAL_HOURS * 3600)  # Convert hours to seconds
            await sync_economic_events_to_db()
        except asyncio.CancelledError:
            logger.info("[news_sync] Worker cancelled, shutting down...")
            break
        except Exception as e:
            logger.error("[news_sync] Sync error: %s", e)
            await asyncio.sleep(60)  # Wait 1 minute before retrying


# Convenience function for one-time sync
async def sync_now() -> Dict[str, Any]:
    """Trigger an immediate sync."""
    return await sync_economic_events_to_db()


# Standalone test
if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("Testing news sync worker...")
        result = await sync_economic_events_to_db()
        print(f"Result: {result}")
        
        # Test cached events
        events = await get_cached_high_impact_events(hours=24)
        print(f"High-impact events (next 24h): {len(events)}")
        for e in events[:5]:
            print(f"  - {e.get('title')} ({e.get('impact')}) @ {e.get('event_date')}")
    
    asyncio.run(test())
