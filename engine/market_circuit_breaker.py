"""
Market Circuit Breaker - Flash Crash Protection

Monitors BTC for sudden crashes and halts all trading when detected.
Cryptocurrency markets are highly correlated to Bitcoin - if BTC 
flashes down significantly, every technical indicator on every altcoin 
will be wrong.

This module provides a system-wide killswitch that halts all new trades 
if the "Market King" (BTC) is experiencing severe volatility.

Usage:
    from engine.market_circuit_breaker import MarketCircuitBreaker
    
    breaker = MarketCircuitBreaker()
    is_safe = await breaker.check_market_health()
    if not is_safe:
        # Skip entire trading cycle
        continue
"""

from __future__ import annotations

import os
import time
import logging
from typing import Optional
import aiohttp

logger = logging.getLogger("CircuitBreaker")


class MarketCircuitBreaker:
    """
    Circuit breaker that monitors BTC for flash crash conditions.
    
    When BTC drops more than threshold percentage within the monitoring 
    window, trading is halted for a configurable duration.
    
    This protects the bot from:
    - False oversold RSI signals during BTC crash
    - False technical breakouts during market-wide selloff
    - Liquidation cascades that affect all assets
    """
    
    def __init__(
        self,
        drop_threshold_pct: float = -4.0,
        # Default: -4% drop triggers circuit breaker
        halt_duration_hours: float = 4.0,
        # Default: halt for 4 hours after trigger
        check_interval_seconds: float = 300.0,
        # Check BTC every 5 minutes
    ):
        self.drop_threshold_pct = float(
            os.getenv(
                "CIRCUIT_BREAKER_DROP_THRESHOLD_PCT",
                str(drop_threshold_pct)
            )
        )
        self.halt_duration_seconds = float(halt_duration_hours) * 3600
        self.check_interval_seconds = float(check_interval_seconds)
        
        self._halt_until: float = 0.0
        self._last_check: float = 0.0
        self._btc_price_cache: dict = {}
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Track BTC price history for velocity calculation
        self._price_history: list = []
        self._max_history_length = 12  # Store up to 12 data points
    
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
    
    async def get_btc_price(self) -> Optional[float]:
        """
        Get current BTC/USDT price from spot market.
        
        Returns:
            Current price or None on failure
        """
        # Check cache first (30 second TTL for price data)
        cached = self._btc_price_cache.get('price')
        cached_time = self._btc_price_cache.get('timestamp', 0)
        if cached and (time.time() - cached_time) < 30:
            return cached
        
        try:
            url = "https://api.binance.com/api/v3/ticker/price"
            params = {"symbol": "BTCUSDT"}
            
            session = await self._get_session()
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                price = float(data.get('price', 0))
                
                if price > 0:
                    self._btc_price_cache = {
                        'price': price,
                        'timestamp': time.time()
                    }
                
                return price if price > 0 else None
                
        except Exception as e:
            logger.debug(f"[circuit_breaker] Failed to get BTC price: {e}")
            return None
    
    async def get_btc_price_1h_ago(self) -> Optional[float]:
        """
        Get BTC price from approximately 1 hour ago.
        
        Uses recent price history to estimate 1-hour ago price.
        This is a simplified version - in production you'd want
        to store this externally or use a more reliable source.
        
        Returns:
            Price 1 hour ago, or None if unavailable
        """
        # For now, we'll check against recent history
        # In production, this should be persisted
        if len(self._price_history) >= 12:
            # 12 * 5min intervals = 60 minutes
            return self._price_history[0]
        return None
    
    def _record_price(self, price: float) -> None:
        """Record a price point for history tracking."""
        self._price_history.append(price)
        if len(self._price_history) > self._max_history_length:
            self._price_history.pop(0)
    
    async def check_market_health(self) -> bool:
        """
        Check if market is healthy for trading.
        
        This method:
        1. Returns False if circuit breaker is triggered (halted)
        2. Returns True if BTC hasn't dropped significantly
        3. Triggers circuit breaker if BTC drops too fast
        
        Returns:
            True if market is healthy, False if circuit breaker is active
        """
        # Check if we're in a halted state
        now = time.time()
        if now < self._halt_until:
            remaining = (self._halt_until - now) / 60
            logger.warning(
                f"🛑 CIRCUIT BREAKER ACTIVE: Engine is paused. "
                f"{remaining:.1f} minutes remaining."
            )
            return False
        
        # Throttle checks to avoid excessive API calls
        if (now - self._last_check) < self.check_interval_seconds:
            return True
        
        self._last_check = now
        
        # Get current price
        current_price = await self.get_btc_price()
        if current_price is None:
            # Fail-open: if we can't get price, allow trading
            logger.debug("[circuit_breaker] Cannot get BTC price, fail-open")
            return True
        
        # Get 1-hour ago price
        price_1h_ago = await self.get_btc_price_1h_ago()
        
        if price_1h_ago is None:
            # Not enough history yet - record this price and allow trading
            self._record_price(current_price)
            logger.debug(
                "[circuit_breaker] Insufficient price history, allowing trading"
            )
            return True
        
        # Calculate percentage change
        pct_change = ((current_price - price_1h_ago) / price_1h_ago) * 100
        
        # Record current price for future history
        self._record_price(current_price)
        
        logger.debug(
            f"[circuit_breaker] BTC: ${price_1h_ago:,.0f} -> ${current_price:,.0f} "
            f"({pct_change:+.2f}%)"
        )
        
        # Check if drop exceeds threshold
        if pct_change <= self.drop_threshold_pct:
            logger.critical(
                f"🚨 FLASH CRASH DETECTED: BTC dropped {pct_change:.2f}% "
                f"(threshold: {self.drop_threshold_pct:.2f}%). "
                f"Halting engine for {self.halt_duration_seconds/3600:.1f} hours."
            )
            self._halt_until = now + self.halt_duration_seconds
            return False
        
        return True
    
    def is_halted(self) -> bool:
        """
        Check if circuit breaker is currently halted.
        
        Returns:
            True if trading is halted, False otherwise
        """
        return time.time() < self._halt_until
    
    def get_halt_remaining_seconds(self) -> float:
        """
        Get remaining halt time in seconds.
        
        Returns:
            Seconds remaining until trading resumes, or 0 if not halted
        """
        if not self.is_halted():
            return 0.0
        return max(0.0, self._halt_until - time.time())
    
    def get_status(self) -> dict:
        """
        Get circuit breaker status for monitoring/dashboard.
        
        Returns:
            Dict with status information
        """
        return {
            "halted": self.is_halted(),
            "halt_until": self._halt_until,
            "halt_remaining_seconds": self.get_halt_remaining_seconds(),
            "drop_threshold_pct": self.drop_threshold_pct,
            "last_check": self._last_check,
        }
    
    def reset(self) -> None:
        """
        Manually reset the circuit breaker.
        
        This can be used to clear a halt state (e.g., after manual review).
        """
        self._halt_until = 0.0
        logger.info("[circuit_breaker] Manual reset - circuit breaker cleared")


# Default instance for easy import
default_market_circuit_breaker = MarketCircuitBreaker()


async def check_market_health() -> bool:
    """
    Convenience function to check market health.
    
    Returns:
        True if market is healthy, False if circuit breaker is active
    """
    return await default_market_circuit_breaker.check_market_health()


def is_halted() -> bool:
    """
    Check if circuit breaker is currently halted.
    
    Returns:
        True if trading is halted
    """
    return default_market_circuit_breaker.is_halted()


def get_status() -> dict:
    """
    Get circuit breaker status.
    
    Returns:
        Dict with status information
    """
    return default_market_circuit_breaker.get_status()
