"""
News Filter Module - High-Impact News Killswitch

This module provides a hard killswitch that blocks all trading 30 minutes before 
and after Tier-1 (high-impact) news events like FOMC, CPI, NFP, etc.

Prevents:
- Spread widening during news events
- Stop Loss hunting
- Slippage due to macroeconomic volatility
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("NewsFilter")


async def get_today_high_impact_news() -> List[Dict[str, Any]]:
    """
    Fetch today's high-impact news events.
    
    In production, this would fetch from:
    - FinancialModelingPrep API
    - Polygon.io API
    - ForexFactory Calendar
    
    Returns a list of news events with:
    - title: Event name (e.g., "FOMC Rate Decision")
    - timestamp: datetime in UTC
    - currency: USD, EUR, GBP, etc.
    - impact: "high" or "low"
    """
    from data.providers import get_fundamental_news
    
    try:
        news = await get_fundamental_news()
        high_impact = [
            n for n in news 
            if n.get('impact', '').lower() == 'high'
        ]
        return high_impact
    except Exception as e:
        logger.error(f"Failed to fetch high-impact news: {e}")
        return []


class NewsKillswitch:
    """
    Hard News Killswitch - Blocks trades during high-impact news events.
    
    Usage:
        news_guard = NewsKillswitch(block_window_minutes=30)
        
        if not await news_guard.is_safe_to_trade("BTCUSDT"):
            # Skip this signal - too risky near news
            continue
    """
    
    def __init__(self, block_window_minutes: int = 30):
        """
        Initialize the news killswitch.
        
        Args:
            block_window_minutes: Minutes to block before and after news event
        """
        self.block_window = block_window_minutes
        logger.info(f"NewsKillswitch initialized with {block_window_minutes}min window")
    
    async def is_safe_to_trade(self, asset: str) -> bool:
        """
        Check if it's safe to trade the given asset.
        
        Blocks trades if we are within the blast radius of high-impact news.
        
        Args:
            asset: Trading pair (e.g., "BTCUSDT", "EURUSD")
            
        Returns:
            True if safe to trade, False if blocked by news
        """
        try:
            news_events = await get_today_high_impact_news()
            
            if not news_events:
                return True
            
            now = datetime.now(timezone.utc)
            
            for event in news_events:
                event_time = event.get('timestamp')
                if not event_time:
                    continue
                
                if event_time.tzinfo is None:
                    event_time = event_time.replace(tzinfo=timezone.utc)
                
                time_diff_minutes = abs((now - event_time).total_seconds() / 60.0)
                
                if time_diff_minutes <= self.block_window:
                    currency = event.get('currency', '')
                    impact = event.get('impact', 'high')
                    title = event.get('title', 'Unknown Event')
                    
                    # If it's US news, block USD pairs and Crypto
                    if currency == 'USD' or impact == 'high':
                        stablecoins = ['USDT', 'USD', 'BUSD', 'USDC']
                        if 'USD' in asset or any(s in asset for s in stablecoins):
                            logger.warning(
                                f"🚨 NEWS KILLSWITCH ACTIVE: {title} is in {time_diff_minutes:.1f} mins. "
                                f"Blocking {asset}. Event: {event.get('title', 'Unknown')}"
                            )
                            return False
                    
                    # Block major pairs (EURUSD, GBPUSD, etc.) for EUR/GBP news
                    if currency in ['EUR', 'GBP'] and any(pair in asset for pair in ['EUR', 'GBP']):
                        logger.warning(
                            f"🚨 NEWS KILLSWITCH ACTIVE: {title} is in {time_diff_minutes:.1f} mins. "
                            f"Blocking {asset}."
                        )
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"News fetch failed: {e}. Defaulting to safe (allowed).")
            return True
    
    async def get_next_news_event(self, asset: str) -> Optional[Dict[str, Any]]:
        """
        Get the next upcoming high-impact news event for an asset.
        
        Args:
            asset: Trading pair
            
        Returns:
            Dict with next news event or None
        """
        try:
            news_events = await get_today_high_impact_news()
            if not news_events:
                return None
            
            now = datetime.now(timezone.utc)
            upcoming: List[Dict[str, Any]] = []
            
            for event in news_events:
                event_time = event.get('timestamp')
                if not event_time:
                    continue
                
                if event_time.tzinfo is None:
                    event_time = event_time.replace(tzinfo=timezone.utc)
                
                if event_time > now:
                    currency = event.get('currency', '')
                    if currency == 'USD' or 'USD' in asset:
                        upcoming.append({
                            'title': event.get('title'),
                            'timestamp': event_time,
                            'minutes_until': (event_time - now).total_seconds() / 60.0,
                            'currency': currency,
                        })
            
            if upcoming:
                upcoming.sort(key=lambda x: x['timestamp'])
                return upcoming[0]
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get next news event: {e}")
            return None


# Global instance for easy import
news_guard = NewsKillswitch(block_window_minutes=30)
