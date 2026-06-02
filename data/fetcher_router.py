"""
data/fetcher_router.py - Multi-Asset Provider Router.

This module routes data fetching to the appropriate provider based on asset class,
with automatic fallback logic when the primary provider fails.

Provider Priority by Asset Class:
- Crypto:     Bybit -> CryptoCompare -> CoinGecko  (bypasses geo-blocks)
- Forex:      OANDA -> Polygon.io -> TwelveData  (high precision for pips)
- Stocks:     Polygon.io -> TwelveData -> Finnhub  (official exchange data)
- Commodities: TwelveData -> Yahoo Finance  (best coverage for Gold/Oil)
"""
import logging
import asyncio
from typing import Dict, List, Optional, Tuple, Callable, Any

logger = logging.getLogger(__name__)

# Asset class enum for type safety
ASSET_CLASSES = ["crypto", "fx", "stock", "commodity"]


class DataRouter:
    """
    Multi-asset data provider router with fallback logic.
    
    Usage:
        router = DataRouter()
        candles = await router.fetch_price("BTCUSDT", "crypto", "1h")
    """
    
    def __init__(self):
        """Initialize providers for each asset class."""
        # Import providers lazily to avoid import errors
        self._providers: Dict[str, List[Tuple[str, Callable]] = {
            "crypto": [],
            "fx": [],
            "stock": [],
            "commodity": [],
        }
        self._initialized = False
    
    def _ensure_initialized(self) -> None:
        """Lazy initialization of provider lists."""
        if self._initialized:
            return
        
        # Crypto providers (ordered by preference)
        try:
            from data.connectors import bybit_get_candles
            self._providers["crypto"].append(("bybit", bybit_get_candles))
        except ImportError:
            pass
        
        try:
            from data.connectors import cryptocompare_get_candles
            self._providers["crypto"].append(("cryptocompare", cryptocompare_get_candles))
        except ImportError:
            pass
        
        try:
            from data.providers import fetch_coingecko_candles
            self._providers["crypto"].append(("coingecko", fetch_coingecko_candles))
        except ImportError:
            pass
        
        # FX providers
        try:
            from data.providers import fetch_oanda_candles
            self._providers["fx"].append(("oanda", fetch_oanda_candles))
        except ImportError:
            pass
        
        try:
            from data.providers import fetch_polygon_candles
            self._providers["fx"].append(("polygon", fetch_polygon_candles))
        except ImportError:
            pass
        
        try:
            from data.providers import fetch_twelvedata_candles
            self._providers["fx"].append(("twelvedata", fetch_twelvedata_candles))
        except ImportError:
            pass
        
        try:
            from data.providers import fetch_yahoo_candles
            self._providers["fx"].append(("yahoo", fetch_yahoo_candles))
        except ImportError:
            pass
        
        # Stock providers
        try:
            from data.providers import fetch_polygon_candles
            self._providers["stock"].append(("polygon", fetch_polygon_candles))
        except ImportError:
            pass
        
        try:
            from data.providers import fetch_twelvedata_candles
            self._providers["stock"].append(("twelvedata", fetch_twelvedata_candles))
        except ImportError:
            pass
        
        try:
            from data.providers import fetch_yahoo_candles
            self._providers["stock"].append(("yahoo", fetch_yahoo_candles))
        except ImportError:
            pass
        
        # Commodity providers
        try:
            from data.providers import fetch_twelvedata_candles
            self._providers["commodity"].append(("twelvedata", fetch_twelvedata_candles))
        except ImportError:
            pass
        
        try:
            from data.providers import fetch_yahoo_candles
            self._providers["commodity"].append(("yahoo", fetch_yahoo_candles))
        except ImportError:
            pass
        
        self._initialized = True
        logger.info("[router] providers initialized: crypto=%d fx=%d stock=%d commodity=%d",
                   len(self._providers["crypto"]), len(self._providers["fx"]),
                   len(self._providers["stock"]), len(self._providers["commodity"]))
    
    def _detect_asset_class(self, symbol: str) -> str:
        """Detect asset class from symbol string."""
        sym = symbol.upper()
        
        # Crypto: USDT/USDC/BTC/ETH/BNB suffix
        if sym.endswith(("USDT", "USDC", "BTC", "ETH", "BNB")):
            return "crypto"
        
        # FX: standard 6-char pairs
        clean = sym.replace("/", "").replace("_", "").replace("-", "")
        if len(clean) == 6 and clean.isalpha():
            fx_currencies = {"EUR", "GBP", "USD", "JPY", "CHF", "CAD", "AUD", "NZD"}
            if clean[:3] in fx_currencies and clean[3:] in fx_currencies:
                return "fx"
        
        # Commodities
        commodities = {"XAU", "XAG", "XPT", "XPD", "WTI", "BRENT", "GOLD", "SILVER", "OIL"}
        for kw in commodities:
            if kw in sym:
                return "commodity"
        
        # Default to stock
        return "stock"
    
    async def fetch_price(
        self, 
        symbol: str, 
        asset_class: Optional[str] = None,
        timeframe: str = "1h",
        timeout: float = 10.0
    ) -> List[Dict[str, Any]]:
        """
        Fetch price data with automatic provider fallback.
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT", "EURUSD")
            asset_class: Override asset class detection ("crypto", "fx", "stock", "commodity")
            timeframe: Chart timeframe ("5m", "15m", "1h", "4h", "1d")
            timeout: Provider timeout in seconds
            
        Returns:
            List of candle dictionaries with timestamp, open, high, low, close, volume
        """
        self._ensure_initialized()
        
        # Auto-detect asset class if not provided
        if not asset_class:
            asset_class = self._detect_asset_class(symbol)
        
        # Get providers for this asset class
        providers = self._providers.get(asset_class, [])
        
        if not providers:
            logger.warning("[router] no providers for asset_class=%s symbol=%s", asset_class, symbol)
            return []
        
        # Try each provider in order
        for provider_name, fetch_func in providers:
            try:
                if asyncio.iscoroutinefunction(fetch_func):
                    candles = await asyncio.wait_for(
                        fetch_func(symbol, timeframe),
                        timeout=timeout
                    )
                else:
                    candles = await asyncio.wait_for(
                        asyncio.to_thread(fetch_func, symbol, timeframe),
                        timeout=timeout
                    )
                
                if candles and len(candles) >= 20:
                    logger.info(
                        "[router] success provider=%s asset_class=%s symbol=%s tf=%s candles=%d",
                        provider_name, asset_class, symbol, timeframe, len(candles)
                    )
                    return candles
                else:
                    logger.warning(
                        "[router] provider=%s returned insufficient data symbol=%s tf=%s",
                        provider_name, symbol, timeframe
                    )
            except asyncio.TimeoutError:
                logger.warning("[router] timeout provider=%s symbol=%s", provider_name, symbol)
            except Exception as e:
                logger.warning("[router] error provider=%s symbol=%s: %s", provider_name, symbol, e)
                continue
        
        # All providers failed
        logger.error("[router] all providers failed asset_class=%s symbol=%s", asset_class, symbol)
        return []
    
    def get_primary_provider(self, asset_class: str) -> Optional[str]:
        """Get the name of the primary provider for an asset class."""
        self._ensure_initialized()
        providers = self._providers.get(asset_class, [])
        return providers[0][0] if providers else None


# Default router instance
_default_router: Optional[DataRouter] = None


def get_router() -> DataRouter:
    """Get or create the default DataRouter instance."""
    global _default_router
    if _default_router is None:
        _default_router = DataRouter()
    return _default_router


async def fetch_candles(
    symbol: str,
    timeframe: str = "1h",
    asset_class: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Convenience function to fetch candles via the default router.
    
    This is the main entry point used by the rest of the codebase.
    """
    router = get_router()
    return await router.fetch_price(symbol, asset_class, timeframe)
