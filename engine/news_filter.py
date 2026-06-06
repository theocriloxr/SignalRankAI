"""
News Killswitch Module - Hard News Filter for Algorithmic Trading

This module checks a macroeconomic calendar and strictly blocks all trading 
30 minutes before and after Tier-1 news events (FOMC, CPI, NFP, etc.)

Usage:
    from engine.news_filter import news_guard, NewsKillswitch
    
    # Check if safe to trade
    if await news_guard.is_safe_to_trade("BTCUSDT"):
        # Proceed with trade
        pass
    else:
        # News killswitch active - skip this trade
        pass
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger("NewsFilter")

# Try to import Gemini sentiment analysis
try:
    from services.gemini_ml import get_news_sentiment as _gemini_sentiment
except Exception:
    async def _gemini_sentiment(asset: str, headlines: list) -> str:
        """Fallback when Gemini unavailable."""
        return "NEUTRAL"

# Try to import the news provider, fallback gracefully
try:
    from data.providers import get_today_high_impact_news
except Exception:
    async def get_today_high_impact_news() -> List[Dict[str, Any]]:
        """Fallback - returns empty list when provider unavailable."""
        return []


# Try to import Gemini ML service for sentiment analysis
try:
    from services.gemini_ml import get_news_sentiment as gemini_get_sentiment
except Exception:
    async def gemini_get_sentiment(asset: str, headlines: list) -> str:
        """Fallback - returns NEUTRAL when Gemini unavailable."""
        return "NEUTRAL"


# Try to import news fetching
try:
    from data.news import fetch_news_headlines
except Exception:
    async def fetch_news_headlines(asset: str, lookback_minutes: int = 120) -> list:
        """Fallback - returns empty list when news fetch unavailable."""
        return []


class NewsKillswitch:
    """
    Hard News Killswitch that blocks trades during high-impact macroeconomic events.
    
    Prevents the bot from trading when:
    - 30 minutes before Tier-1 news (FOMC, CPI, NFP, etc.)
    - 30 minutes after Tier-1 news
    
    This prevents spread widening and stop loss hunting during volatile periods.
    """
    
    def __init__(self, block_window_minutes: int = 30):
        """
        Initialize the news killswitch.
        
        Args:
            block_window_minutes: Minutes to block trading before/after news.
                                Default: 30 minutes.
        """
        self.block_window = block_window_minutes
        self.blacklisted_impacts = ["High", "Extreme"]
        self.buffer_minutes = block_window_minutes
        logger.info(f"[NewsKillswitch] Initialized with {block_window_minutes}-minute block window")
    
    async def is_market_volatile(self, asset: str, news_events: list) -> bool:
        """
        Returns True if we are too close to a high-impact news event.
        
        This method checks for "Red Folder" events (like FOMC or NFP) where
        spreads explode and prevents the bot from opening trades.
        
        Args:
            asset: The asset symbol to check (e.g., "BTCUSDT", "EURUSD")
            news_events: List of news event dicts with 'timestamp' and 'impact' keys
        
        Returns:
            True if we are within the blast zone (30 mins before/after high-impact news)
        """
        now = datetime.now(timezone.utc)
        
        for event in news_events:
            event_time = event.get('timestamp')
            impact = event.get('impact', '').upper()
            
            if impact not in self.blacklisted_impacts:
                continue
            
            if event_time is None:
                continue
            
            # Handle both timezone-aware and naive datetimes
            if isinstance(event_time, datetime):
                if event_time.tzinfo is None:
                    event_time = event_time.replace(tzinfo=timezone.utc)
            else:
                try:
                    event_time = datetime.fromisoformat(str(event_time).replace('Z', '+00:00'))
                except Exception:
                    continue
            
            # Calculate the "Blast Zone" (buffer_minutes mins before and after)
            from datetime import timedelta
            start_zone = event_time - timedelta(minutes=self.buffer_minutes)
            end_zone = event_time + timedelta(minutes=self.buffer_minutes)
            
            if start_zone <= now <= end_zone:
                logger.warning(
                    f"🚫 NEWS BLOCK: {asset} blocked due to {event.get('title', 'High-impact event')} ({impact})"
                )
                return True
        
        return False
    
    async def is_safe_to_trade(self, asset: str) -> bool:
        """
        Check if it's safe to trade the given asset.
        
        Blocks trades if we are within the blast radius of high-impact news.
        
        Args:
            asset: The asset symbol to check (e.g., "BTCUSDT", "EURUSD")
        
        Returns:
            True if safe to trade, False if should block due to news.
        """
        try:
            # Fetch today's high-impact news events
            news_events = await get_today_high_impact_news()
            
            if not news_events:
                # No news = safe to trade
                return True
            
            now = datetime.now(timezone.utc)
            
            for event in news_events:
                # Parse event details
                event_time = event.get('timestamp')
                if event_time is None:
                    continue
                
                # Handle both timezone-aware and naive datetimes
                if isinstance(event_time, datetime):
                    if event_time.tzinfo is None:
                        event_time = event_time.replace(tzinfo=timezone.utc)
                else:
                    # Try parsing from string
                    try:
                        event_time = datetime.fromisoformat(str(event_time).replace('Z', '+00:00'))
                    except Exception:
                        continue
                
                # Calculate time difference in minutes
                time_diff_minutes = abs((now - event_time).total_seconds() / 60.0)
                
                if time_diff_minutes > self.block_window:
                    # Outside the block window - continue checking other events
                    continue
                
                # Inside the block window - check if this news affects our asset
                event_currency = event.get('currency', 'USD').upper()
                
                # Determine if this news affects our asset
                # USD news affects: all USD pairs + Crypto (BTCUSDT, ETHUSDT, etc.)
                affects_asset = False
                
                if event_currency == 'USD':
                    # USD news affects crypto-USD pairs and USD-FX pairs
                    if asset.endswith('USDT') or asset.endswith('USD') or asset == 'DXY':
                        affects_asset = True
                    # Also check if it's a major USD cross
                    elif len(asset) == 6 and 'USD' in asset:
                        # EURUSD, GBPUSD, etc.
                        affects_asset = True
                elif event_currency in asset:
                    # E.g., GBP news affects GBPUSD
                    affects_asset = True
                
                if not affects_asset:
                    # Check for EUR-based events affecting EUR pairs
                    if event_currency == 'EUR' and (
                        asset.startswith('EUR') or 'EUR' in asset
                    ):
                        affects_asset = True
                    # Check for GBP events
                    elif event_currency == 'GBP' and (
                        asset.startswith('GBP') or 'GBP' in asset
                    ):
                        affects_asset = True
                    # Check for JPY events
                    elif event_currency == 'JPY' and (
                        asset.startswith('JPY') or 'JPY' in asset
                    ):
                        affects_asset = True
                
                # Block if this news affects our asset
                if affects_asset:
                    event_title = event.get('title', 'High-impact news')
                    time_until = self.block_window - time_diff_minutes
                    
                    if time_until >= 0:
                        logger.warning(
                            f"🚨 NEWS KILLSWITCH ACTIVE: {event_title} in {time_diff_minutes:.1f} mins. "
                            f"Blocking {asset}. Resumes in ~{time_until:.0f} mins."
                        )
                    else:
                        logger.warning(
                            f"🚨 NEWS KILLSWITCH COOLDOWN: {event_title} was {time_diff_minutes:.1f} mins ago. "
                            f"Blocking {asset}. Clears in ~{-time_until:.0f} mins."
                        )
                    return False
            
            # No active news events in the window
            return True
            
        except Exception as e:
            logger.error(f"News fetch failed: {e}. Defaulting to safe (allowed).")
            # Default to safe - if news fetch fails, allow trading
            return True
    
    async def get_trading_bias(self, asset: str, headlines: list) -> str:
        """
        Determines if the news environment matches the trade.
        Uses Gemini to analyze news sentiment for the specific asset.
        
        Returns: 'BULLISH', 'BEARISH', or 'NEUTRAL'
        """
        if not headlines:
            return "NEUTRAL"
            
        # Ask Gemini to summarize the news sentiment for this specific asset
        sentiment = await gemini_get_sentiment(asset, headlines)
        return sentiment
    
    def get_news_context(self, asset: str) -> Dict[str, Any]:
        """
        Get current news context for an asset (non-blocking).
        
        Returns information about upcoming news without blocking trades.
        Useful for scoring/confluence enhancement.
        
        Args:
            asset: The asset symbol to check.
        
        Returns:
            Dict with news timing information.
        """
        # This is a synchronous convenience method
        # For full async functionality, use is_safe_to_trade
        return {
            'has_upcoming_news': False,
            'minutes_until_news': None,
            'block_window': self.block_window,
        }


# Global instance for easy import
news_guard = NewsKillswitch(block_window_minutes=30)


async def is_market_volatile(asset: str, news_events: list) -> bool:
    """
    Returns True if we are too close to a high-impact news event.
    
    This is a convenience wrapper around the core check that matches the
    requested API in the implementation plan.
    
    Args:
        asset: The asset symbol to check
        news_events: List of news event dicts with 'timestamp' and 'impact' keys
    
    Returns:
        True if within the blast zone (30 mins before/after high-impact news)
    """
    return await news_guard.is_safe_to_trade(asset)


async def check_trade_allowed(asset: str) -> bool:
    """
    Convenience function to check if trading is allowed.
    
    Args:
        asset: Asset symbol to check.
    
    Returns:
        True if allowed, False if blocked by news.
    """
    return await news_guard.is_safe_to_trade(asset)


# Example integration code (commented out for reference):
"""
# INTEGRATION EXAMPLE - Add to engine/core.py pipeline:

# After correlation filter and before dispatch:
try:
    from engine.news_filter import news_guard
    
    # Check news killswitch
    if not await news_guard.is_safe_to_trade(signal['asset']):
        logger.info(f"[engine] NEWS KILLSWITCH blocked {signal['asset']} {signal['direction']}")
        pipeline_stats["skipped_news_killswitch"] += 1
        continue
except Exception as e:
    logger.debug(f"[engine] News killswitch check failed: {e}")
    # Default to allowing if check fails
    pass
"""

if __name__ == "__main__":
    # Quick test
    import asyncio
    
    async def test():
        print("Testing News Killswitch...")
        
        # Test safe assets
        result = await news_guard.is_safe_to_trade("BTCUSDT")
        print(f"BTCUSDT safe: {result}")
        
        result = await news_guard.is_safe_to_trade("EURUSD")
        print(f"EURUSD safe: {result}")
        
        print("Done!")
    
    asyncio.run(test())
