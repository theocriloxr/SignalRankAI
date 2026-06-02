"""
data/fetcher_router.py - Multi-Asset Provider Router

Routes data fetching requests to the appropriate provider based on asset class.
This ensures that if one provider is blocked, the system can fall back to alternative providers.

Provider Priority by Asset Class:
- Crypto:     Binance -> Bybit -> CryptoCompare (bypasses geo-blocks)
- Forex:     AlphaVantage -> OANDA -> TwelveData (high precision for pips)
- Stocks:    Polygon.io -> TwelveData -> Finnhub (official exchange data)
- Commodities: TwelveData -> Yahoo Finance (best coverage for Gold/Oil)

Usage:
    from data.fetcher_router import DataRouter
    
    router = DataRouter()
    candles = await router.fetch_price("BTCUSDT", "crypto")
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Any

from data.fetcher import get_candles, get_asset_type
from data.providers import (
    fetch_polygon_candles,
    fetch_twelvedata_candles,
    fetch_oanda_candles,
    fetch_yahoo_candles,
    fetch_cryptocompare_candles,
)

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when a provider hits rate limits."""
    pass


class DataRouter:
    """
    Multi-asset data provider router with fallback logic.
    
    Routes fetch requests to the appropriate provider based on asset class.
    Implements automatic fallback when primary provider fails.
    """
    
    def __init__(self):
        # Initialize provider instances
        self._providers_initialized = False
        self._init_providers()
    
    def _init_providers(self):
        """Lazy initialization of providers."""
        if self._providers_initialized:
            return
            
        # Primary providers per asset class
        self.crypto_provider = "bybit"
        self.equity_provider = "polygon"
        self.macro_provider = "twelvedata"
        self.fx_provider = "oanda"
        
        self._providers_initialized = True
        logger.info("[router] providers initialized")
    
    async def fetch_price(self, symbol: str, asset_class: str) -> list:
        """
        Fetch price data using the appropriate provider for the asset class.
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT", "EURUSD", "AAPL")
            asset_class: Asset class ("crypto", "fx", "stock", "commodity")
            
        Returns:
            List of candle dictionaries
        """
        try:
            if asset_class == "crypto":
                return await self._fetch_crypto(symbol)
            elif asset_class in ["stock", "commodity"]:
                return await self._fetch_traditional(symbol)
            elif asset_class == "fx":
                return await self._fetch_fx(symbol)
            else:
                # Default fallback
                return await self._fetch_crypto(symbol)
        except RateLimitError:
            # Fallback logic here
            logger.warning(f"[router] rate limit hit for {symbol}, trying fallback")
            return await self._fetch_fallback(symbol, asset_class)
    
    async def _fetch_crypto(self, symbol: str) -> list:
        """Fetch crypto data - primary: Bybit, fallback: CryptoCompare."""
        # Try Bybit first (CCXT-based, bypasses geo-blocks)
        try:
            candles = await self._try_provider(symbol, "bybit")
            if candles and len(candles) >= 20:
                return candles
        except Exception as e:
            logger.warning(f"[router] bybit failed: {e}")
        
        # Fallback to CryptoCompare
        try:
            candles = await self._try_provider(symbol, "cryptocompare")
            if candles and len(candles) >= 20:
                return candles
        except Exception as e:
            logger.warning(f"[router] cryptocompare failed: {e}")
        
        # Final fallback to CoinGecko
        return await self._try_provider(symbol, "coingecko")
    
    async def _fetch_fx(self, symbol: str) -> list:
        """Fetch FX data - primary: OANDA, fallback: TwelveData."""
        # Try OANDA first (bank-grade precision)
        try:
            candles = await self._try_provider(symbol, "oanda")
            if candles and len(candles) >= 20:
                return candles
        except Exception as e:
            logger.warning(f"[router] oanda failed: {e}")
        
        # Fallback to TwelveData
        try:
            candles = await self._try_provider(symbol, "twelvedata")
            if candles and len(candles) >= 20:
                return candles
        except Exception as e:
            logger.warning(f"[router] twelvedata failed: {e}")
        
        # Final fallback to Polygon
        return await self._try_provider(symbol, "polygon")
    
    async def _fetch_traditional(self, symbol: str) -> list:
        """Fetch stock/commodity data - primary: Polygon, fallback: TwelveData."""
        # Try Polygon first (premium, official exchange data)
        try:
            candles = await self._try_provider(symbol, "polygon")
            if candles and len(candles) >= 20:
                return candles
        except Exception as e:
            logger.warning(f"[router] polygon failed: {e}")
        
        # Fallback to TwelveData
        try:
            candles = await self._try_provider(symbol, "twelvedata")
            if candles and len(candles) >= 20:
                return candles
        except Exception as e:
            logger.warning(f"[router] twelvedata failed: {e}")
        
        # Final fallback to Yahoo Finance
        return await self._try_provider(symbol, "yahoo")
    
    async def _try_provider(self, symbol: str, provider: str, timeframe: str = "1h") -> list:
        """Try a specific provider with error handling."""
        import asyncio
        
        def _sync_fetch():
            if provider == "bybit":
                return fetch_bybit_candles(symbol, timeframe)
            elif provider == "cryptocompare":
                return fetch_cryptocompare_candles(symbol, timeframe)
            elif provider == "polygon":
                return fetch_polygon_candles(symbol, timeframe, "stocks")
            elif provider == "twelvedata":
                return fetch_twelvedata_candles(symbol, timeframe, "stocks")
            elif provider == "oanda":
                return fetch_oanda_candles(symbol, timeframe)
            elif provider == "yahoo":
                return fetch_yahoo_candles(symbol, timeframe)
            elif provider == "coingecko":
                from data.providers import fetch_coingecko_candles
                return fetch_coingecko_candles(symbol, timeframe)
            return []
        
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_sync_fetch),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            raise RateLimitError(f"{provider} timeout")
        except Exception as e:
            if "429" in str(e) or "rate limit" in str(e).lower():
                raise RateLimitError(f"{provider} rate limited")
            raise
    
    async def _fetch_fallback(self, symbol: str, asset_class: str) -> list:
        """Generic fallback using multi-provider fetcher."""
        # Use the main fetcher which already has fallbacks
        try:
            import asyncio
            return await asyncio.to_thread(lambda: get_candles(symbol, "1h"))
        except Exception:
            return []


# Default router instance
_default_router: Optional[DataRouter] = None


def get_router() -> DataRouter:
    """Get the default router instance."""
    global _default_router
    if _default_router is None:
        _default_router = DataRouter()
    return _default_router


async def fetch_with_router(symbol: str, timeframe: str = "1h") -> list:
    """
    Convenience function to fetch data using the router.
    
    Auto-detects asset class and routes to appropriate provider.
    """
    router = get_router()
    asset_class = get_asset_type(symbol)
    return await router.fetch_price(symbol, asset_class)
