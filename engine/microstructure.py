"""
Order Book Microstructure Analyzer
Checks the live order book depth to detect institutional "walls" before approving trades.

Technical analysis might indicate a "BUY" signal, but if there's a massive 
"Sell Wall" above current price, the breakout will fail 90% of the time.

This module provides a leading indicator check before trade execution.
"""

import os
import logging
from typing import Optional, Dict, Any
import aiohttp

logger = logging.getLogger(__name__)


class OrderBookAnalyzer:
    """Analyzes order book imbalance to validate trade direction."""
    
    def __init__(self, imbalance_threshold: float = 1.5):
        """
        Initialize the order book analyzer.
        
        Args:
            imbalance_threshold: Ratio threshold for wall detection.
                               If Ask > Bid * threshold, it's a sell wall.
                               If Bid > Ask * threshold, it's a buy wall.
                               Default 1.5 means 50% more volume on one side = wall.
        """
        self.imbalance_threshold = float(
            os.getenv("ORDER_BOOK_IMBALANCE_THRESHOLD", str(imbalance_threshold))
        )
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def fetch_order_book(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch order book from Binance public API.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            
        Returns:
            Order book data dict or None on failure.
        """
        # Use Binance public API (no auth required for depth)
        url = f"https://api.binance.com/api/v3/depth"
        params = {
            "symbol": symbol.upper(),
            "limit": 50  # Top 50 levels
        }
        
        try:
            session = await self._get_session()
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    logger.warning(f"[microstructure] Order book API returned {response.status}")
                    return None
                data = await response.json()
                return data
        except Exception as e:
            logger.debug(f"[microstructure] Order book fetch failed: {e}")
            return None
    
    def calculate_volume(self, orders: list) -> float:
        """
        Calculate total volume from order book levels.
        
        Args:
            orders: List of [price, quantity] pairs from order book.
            
        Returns:
            Total volume (price * quantity).
        """
        total = 0.0
        for order in orders:
            try:
                if isinstance(order, list) and len(order) >= 2:
                    price = float(order[0])
                    qty = float(order[1])
                    total += price * qty
            except (ValueError, TypeError):
                continue
        return total
    
    async def check_path_clear(
        self, 
        symbol: str, 
        direction: str,
        include_spread_check: bool = True
    ) -> tuple[bool, str]:
        """
        Check if the path is clear for a trade based on order book.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            direction: 'LONG' or 'SHORT'
            include_spread_check: If True, also check for wide spreads (low liquidity)
            
        Returns:
            Tuple of (path_clear: bool, reason: str).
            - (True, "ok") = path clear, proceed with trade
            - (False, "sell_wall") = sell wall detected, block LONG
            - (False, "buy_wall") = buy wall detected, block SHORT
            - (False, "wide_spread") = spread too wide, low liquidity warning
            - (False, "api_error") = could not fetch data, fail-open allowed
        """
        data = await self.fetch_order_book(symbol)
        
        if not data:
            # Fail-open: don't block trades if API fails
            return True, "api_error"
        
        bids = data.get('bids', [])
        asks = data.get('asks', [])
        
        if not bids or not asks:
            return True, "empty_book"
        
        # Calculate total volume
        bid_volume = self.calculate_volume(bids)
        ask_volume = self.calculate_volume(asks)
        
        if bid_volume <= 0 or ask_volume <= 0:
            return True, "empty_levels"
        
        # Check for SELL WALL (for LONG trades)
        if direction.upper() in ("LONG", "BUY"):
            if ask_volume > (bid_volume * self.imbalance_threshold):
                logger.warning(
                    f"[microstructure] 🧱 SELL WALL on {symbol}: "
                    f"AskVol={ask_volume:.0f} > BidVol={bid_volume:.0f} × {self.imbalance_threshold}. "
                    f"Vetoing LONG."
                )
                return False, "sell_wall"
        
        # Check for BUY WALL (for SHORT trades)
        elif direction.upper() in ("SHORT", "SELL"):
            if bid_volume > (ask_volume * self.imbalance_threshold):
                logger.warning(
                    f"[microstructure] 🧱 BUY WALL on {symbol}: "
                    f"BidVol={bid_volume:.0f} > AskVol={ask_volume:.0f} × {self.imbalance_threshold}. "
                    f"Vetoing SHORT."
                )
                return False, "buy_wall"
        
        # Optional spread check (liquidity indicator)
        if include_spread_check:
            try:
                best_bid = float(bids[0][0])
                best_ask = float(asks[0][0])
                spread = best_ask - best_bid
                spread_pct = (spread / best_bid) * 100 if best_bid > 0 else 0
                
                # Warn if spread > 0.5% (very wide for most assets)
                if spread_pct > 0.5:
                    logger.warning(
                        f"[microstructure] ⚠️ Wide spread on {symbol}: "
                        f"{spread_pct:.2f}% - low liquidity warning"
                    )
                    # Don't block, just warn
                    
            except (ValueError, TypeError, IndexError):
                pass
        
        return True, "ok"
    
    async def get_imbalance_ratio(self, symbol: str) -> Optional[float]:
        """
        Get the current order book imbalance ratio.
        
        Args:
            symbol: Trading symbol.
            
        Returns:
            Ratio (ask_volume / bid_volume) or None on failure.
        """
        data = await self.fetch_order_book(symbol)
        
        if not data:
            return None
        
        bids = data.get('bids', [])
        asks = data.get('asks', [])
        
        if not bids or not asks:
            return None
        
        bid_volume = self.calculate_volume(bids)
        ask_volume = self.calculate_volume(asks)
        
        if bid_volume <= 0:
            return None
            
        return ask_volume / bid_volume


# Default instance for easy import
default_order_book_analyzer = OrderBookAnalyzer()


async def check_order_book(
    symbol: str, 
    direction: str
) -> tuple[bool, str]:
    """
    Convenience function for order book check.
    
    Args:
        symbol: Trading symbol.
        direction: 'LONG' or 'SHORT'.
        
    Returns:
        Tuple of (path_clear, reason).
    """
    return await default_order_book_analyzer.check_path_clear(symbol, direction)
