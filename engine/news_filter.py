"""
News Filter - Hard News Killswitch

Blocks all trading 30 minutes before and after Tier-1 macroeconomic news events.
Prevents stop hunt and spread widening during high-impact news like FOMC, CPI, NFP.
"""

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

logger = logging.getLogger("NewsFilter")


class NewsKillswitch:
    """
    A hard killswitch that blocks trades during high-impact news events.
    
    When US high-impact news (FOMC, CPI, NFP) is within the block window,
    we block all USD pairs and Crypto (BTCUSDT, ETHUSDT) to prevent stop hunting.
    """
    
    def __init__(self, block_window_minutes: int = 30):
        """
        Args:
            block_window_minutes: Minutes before/after news to block trading (default: 30)
        """
        self.block_window = block_window_minutes
        self._cached_news: Optional[List[dict]] = None
        self._last_fetch: Optional[datetime] = None
    
    async def is_safe_to_trade(self, asset: str) -> bool:
        """
        Blocks trades if within blast radius of high-impact news.
        
        Args:
            asset: Asset symbol (e.g., 'BTCUSDT', 'EURUSD')
            
        Returns:
            True if safe to trade, False if news killswitch is active
        """
        try:
            news_events = await self._fetch_today_high_impact_news()
            now = datetime.now(timezone.utc)
            
            for event in news_events:
                event_time = event.get('timestamp')  # type: ignore
                if not event_time:
                    continue
                    
                # Handle both datetime objects and ISO strings
                if isinstance(event_time, str):
                    event_time = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
                
                time_diff_minutes = abs((now - event_time).total_seconds() / 60.0)
                
                if time_diff_minutes <= self.block_window:
                    # Check if it's US news affecting this asset
                    currency = str(event.get('currency', ''))
                    impact = str(event.get('impact', '')).lower()
                    
                    # Block USD pairs and Crypto during US high-impact news
                    if currency == 'USD' or impact == 'high':
                        is_usd_asset = 'USD' in asset or asset in ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
                        is_crypto = asset.endswith(('USDT', 'USDC', 'BUSD'))
                        
                        if is_usd_asset or is_crypto:
                            logger.warning(
                                f"🚨 NEWS KILLSWITCH ACTIVE: {event.get('title', 'Unknown')} "
                                f"in {time_diff_minutes:.1f} mins. Blocking {asset}."
                            )
                            return False
                            
            return True
            
        except Exception as e:
            logger.error(f"News fetch failed: {e}. Defaulting to safe (allowed).")
            return True
    
    async def _fetch_today_high_impact_news(self) -> List[dict]:
        """
        Fetch today's high-impact news events.
        
        Try multiple providers in order:
        1. Financial Modeling Prep (configured)
        2. Polygon
        3. Fallback to empty list
        """
        # Check cache (valid for 5 minutes)
        cache_ttl_seconds = 300
        if self._cached_news and self._last_fetch:
            age = (datetime.now(timezone.utc) - self._last_fetch).total_seconds()
            if age < cache_ttl_seconds:
                return self._cached_news  # type: ignore
        
        news_events: List[dict] = []
        
        # Try Financial Modeling Prep
        try:
            from data.providers import get_today_high_impact_news
            news_events = await get_today_high_impact_news()  # type: ignore
        except Exception as e:
            logger.debug(f"FMP news unavailable: {e}")
        
        # Try Polygon as fallback
        if not news_events:
            try:
                from data.alternative_providers import get_polygon_news
                news_events = await get_polygon_news()  # type: ignore
            except Exception as e:
                logger.debug(f"Polygon news unavailable: {e}")
        
        # Cache results
        self._cached_news = news_events  # type: ignore
        self._last_fetch = datetime.now(timezone.utc)
        
        return news_events
    
    def get_next_high_impact_news(self) -> Optional[dict]:
        """
        Get the next upcoming high-impact news event.
        
        Returns:
            Dict with 'title', 'timestamp', 'currency', 'impact' or None
        """
        try:
            news = self._cached_news or []
            now = datetime.now(timezone.utc)
            
            for event in news:
                event_time = event.get('timestamp')  # type: ignore
                if isinstance(event_time, str):
                    event_time = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
                
                if event_time and event_time > now:
                    return event  # type: ignore
                    
        except Exception as e:
            logger.error(f"Failed to get next news: {e}")
            
        return None


# Global instance for easy import
news_guard = NewsKillswitch()


async def is_safe_to_trade(asset: str) -> bool:
    """Convenience function using global news_guard instance."""
    return await news_guard.is_safe_to_trade(asset)
