"""
Derivatives Squeeze Detector - Institutional Grade Microstructure Filter

Checks Binance USD-M Futures for Funding Rate imbalances to detect "Long Squeeze" 
or "Short Squeeze" conditions. When funding rate is highly positive, retail 
traders are over-leveraged LONG, meaning market makers will likely drop the 
price to liquidate them (Squeeze).

This module provides a leading indicator check before trade execution.

Usage:
    from engine.derivatives import SqueezeDetector
    
    detector = SqueezeDetector()
    bias = await detector.get_squeeze_bias("BTCUSDT")
    # Returns: 'BULLISH', 'BEARISH', or 'NEUTRAL'
"""

from __future__ import annotations

import os
import logging
from typing import Optional
import aiohttp

logger = logging.getLogger("DerivativesAlpha")


class SqueezeDetector:
    """
    Detects derivatives market squeeze conditions using Binance Funding Rates.
    
    When funding rate is heavily positive (> 0.05% per 8h), longs are paying to maintain 
    positions - indicating over-leveraged long side. Market makers often squeeze/liquidate 
    these positions, making SHORT signals more profitable.
    
    When funding rate is heavily negative (< -0.05% per 8h), shorts are paying - 
    indicating over-leveraged short side. Market makers often squeeze/liquidate 
    these positions, making LONG signals more profitable.
    """
    
    def __init__(
        self,
        extreme_funding_threshold: float = 0.0005,
        # 0.05% per 8 hours is considered extreme in crypto
    ):
        self.extreme_funding_threshold = float(
            os.getenv(
                "SQUEEZE_FUNDING_THRESHOLD", 
                str(extreme_funding_threshold)
            )
        )
        self._session: Optional[aiohttp.ClientSession] = None
        self._btc_price_cache: dict = {}
        self._cache_ttl_seconds = 300  # 5 minutes cache for BTC price
    
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
    
    async def get_squeeze_bias(self, asset: str) -> str:
        """
        Checks Binance USD-M Futures for Funding Rate imbalances.
        
        Args:
            asset: Trading symbol (e.g., 'BTCUSDT')
            
        Returns:
            'BULLISH' - Shorts are trapped, going LONG is advantageous
            'BEARISH' - Longs are over-leveraged, going SHORT is advantageous  
            'NEUTRAL' - No extreme funding rate detected, or API failure
        """
        # Only works for USDT perpetual pairs
        if not asset.endswith("USDT"):
            logger.debug(f"[derivatives] {asset} is not USDT pair, skipping funding check")
            return "NEUTRAL"
        
        try:
            # Public Binance Futures API (No keys required)
            url = f"https://fapi.binance.com/fapi/v1/premiumIndex"
            params = {"symbol": asset.upper()}
            
            session = await self._get_session()
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    logger.debug(
                        f"[derivatives] Funding API returned {response.status} "
                        f"for {asset}, defaulting to NEUTRAL"
                    )
                    return "NEUTRAL"
                
                data = await response.json()
                funding_rate = float(data.get('lastFundingRate', 0))
                
                # Log the funding rate for debugging
                funding_rate_pct = funding_rate * 100
                logger.debug(
                    f"[derivatives] {asset} funding rate: {funding_rate_pct:.4f}% "
                    f"(threshold: ±{self.extreme_funding_threshold * 100:.4f}%)"
                )
                
                # Check for Long Squeeze (over-leveraged longs)
                if funding_rate >= self.extreme_funding_threshold:
                    logger.warning(
                        f"🧲 SQUEEZE DETECTED: {asset} Longs are over-leveraged "
                        f"(Funding: {funding_rate_pct:.4f}%). "
                        f"Bias: BEARISH. Veto LONG signals."
                    )
                    return "BEARISH"
                
                # Check for Short Squeeze (over-leveraged shorts)
                elif funding_rate <= -self.extreme_funding_threshold:
                    logger.warning(
                        f"🧲 SQUEEZE DETECTED: {asset} Shorts are trapped "
                        f"(Funding: {funding_rate_pct:.4f}%). "
                        f"Bias: BULLISH. Veto SHORT signals."
                    )
                    return "BULLISH"
                
                # Neutral - no extreme funding rate
                return "NEUTRAL"
                
        except Exception as e:
            logger.debug(
                f"[derivatives] Funding rate check failed for {asset}: {e}. "
                f"Defaulting to NEUTRAL (fail-open)"
            )
            return "NEUTRAL"
    
    async def get_funding_rate(self, asset: str) -> Optional[float]:
        """
        Get the raw funding rate for an asset.
        
        Args:
            asset: Trading symbol
            
        Returns:
            Funding rate as float (e.g., 0.0001 = 0.01%), or None on failure
        """
        if not asset.endswith("USDT"):
            return None
            
        try:
            url = f"https://fapi.binance.com/fapi/v1/premiumIndex"
            params = {"symbol": asset.upper()}
            
            session = await self._get_session()
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                return float(data.get('lastFundingRate', 0))
                
        except Exception as e:
            logger.debug(f"[derivatives] Failed to get funding rate for {asset}: {e}")
            return None
    
    async def get_btc_price(self) -> Optional[float]:
        """
        Get current BTC/USDT price from spot market.
        
        Returns:
            Current price or None on failure
        """
        import time
        
        # Check cache first
        cached = self._btc_price_cache.get('price')
        cached_time = self._btc_price_cache.get('timestamp', 0)
        if cached and (time.time() - cached_time) < self._cache_ttl_seconds:
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
            logger.debug(f"[derivatives] Failed to get BTC price: {e}")
            return None
    
    async def check_veto(self, asset: str, signal_direction: str) -> tuple[bool, str]:
        """
        Check if a signal should be vetoed due to squeeze conditions.
        
        Args:
            asset: Trading symbol
            signal_direction: 'LONG' or 'SHORT'
            
        Returns:
            Tuple of (should_veto: bool, reason: str)
        """
        bias = await self.get_squeeze_bias(asset)
        signal_dir = signal_direction.upper()
        
        # Veto LONG when bias is BEARISH (longs over-leveraged)
        if signal_dir in ("LONG", "BUY") and bias == "BEARISH":
            return True, f"veto_long_squeeze_bias_{bias}"
        
        # Veto SHORT when bias is BULLISH (shorts over-leveraged)
        if signal_dir in ("SHORT", "SELL") and bias == "BULLISH":
            return True, f"veto_short_squeeze_bias_{bias}"
        
        return False, "ok"


# Default instance for easy import
default_squeeze_detector = SqueezeDetector()


async def get_squeeze_bias(asset: str) -> str:
    """
    Convenience function to get squeeze bias.
    
    Args:
        asset: Trading symbol
        
    Returns:
        'BULLISH', 'BEARISH', or 'NEUTRAL'
    """
    return await default_squeeze_detector.get_squeeze_bias(asset)


async def check_veto(asset: str, signal_direction: str) -> tuple[bool, str]:
    """
    Convenience function to check if signal should be vetoed.
    
    Args:
        asset: Trading symbol
        signal_direction: 'LONG' or 'SHORT'
        
    Returns:
        Tuple of (should_veto, reason)
    """
    return await default_squeeze_detector.check_veto(asset, signal_direction)
