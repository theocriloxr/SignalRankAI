"""
data/fetcher_router.py - Multi-Asset Provider Router

Routes data fetching to the appropriate provider based on asset class.
This ensures that if one provider is blocked, the system falls back to alternatives.

Provider Priority (from config.py or defaults):
- Crypto:     Bybit -> CryptoCompare -> CoinGecko (bypasses geo-blocks)
- Forex:      Polygon.io -> Twelve Data -> OANDA (high precision for pips)
- Stocks:     Polygon.io -> Twelve Data -> Finnhub (official SIP data)
- Commodities: Twelve Data -> Yahoo Finance (best Gold/Oil coverage)

Usage:
    from data.fetcher_router import DataRouter
    
    router = DataRouter()
    candles = await router.fetch_price("BTCUSDT", "crypto")
"""
import os
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


# Provider health tracking for automatic fallback
_PROVIDER_HEALTH: Dict[str, Dict[str, Any]] = {}


def _mark_provider_result(provider_name: str, ok: bool) -> None:
    """Track provider success/failure for intelligent fallback."""
    if provider_name not in _PROVIDER_HEALTH:
        _PROVIDER_HEALTH[provider_name] = {"failures": 0, "successes": 0}
    
    if ok:
        _PROVIDER_HEALTH[provider_name]["successes"] += 1
    else:
        _PROVIDER_HEALTH[provider_name]["failures"] += 1


def _is_provider_healthy(provider_name: str) -> bool:
    """Check if provider is healthy (not having too many failures)."""
    if provider_name not in _PROVIDER_HEALTH:
        return True
    stats = _PROVIDER_HEALTH[provider_name]
    total = stats["failures"] + stats["successes"]
    if total < 3:
        return True
    # If failure rate > 50%, mark unhealthy
    return stats["failures"] / total < 0.5


class DataRouter:
    """Routes data fetching to appropriate providers based on asset class."""
    
    def __init__(self):
        self._providers_initialized = False
        self._init_providers()
    
    def _init_providers(self) -> None:
        """Initialize provider instances lazily."""
        if self._providers_initialized:
            return
        
        # Crypto providers (CCXT-based)
        self._crypto_providers: List[tuple[str, callable]] = []
        self._fx_providers: List[tuple[str, callable]] = []
        self._stock_providers: List[tuple[str, callable]] = []
        self._commodity_providers: List[tuple[str, callable]] = []
        
        # Try importing from connectors first, then fall back to legacy providers
        try:
            from data import connectors as conn
            self._connectors = conn
        except ImportError:
            self._connectors = None
        
        try:
            from data import providers as prov
            self._legacy_providers = prov
        except ImportError:
            self._legacy_providers = None
        
# Crypto: Bybit -> CryptoCompare -> CoinGecko -> Yahoo (yfinance - no API key needed, no geo-block)
        self._crypto_providers = [
            ("bybit", self._get_bybit_candles),
            ("cryptocompare", self._get_cryptocompare_candles),
            ("coingecko", self._get_coingecko_candles),
            ("yahoo", self._get_yahoo_candles),
        ]
        
        # Forex: Polygon -> Twelve Data -> OANDA
        self._fx_providers = [
            ("polygon", self._get_polygon_candles),
            ("twelvedata", self._get_twelvedata_candles),
            ("oanda", self._get_oanda_candles),
            ("yahoo", self._get_yahoo_candles),
        ]
        
        # Stocks: Polygon -> Twelve Data -> Yahoo
        self._stock_providers = [
            ("polygon", self._get_polygon_candles),
            ("twelvedata", self._get_twelvedata_candles),
            ("yahoo", self._get_yahoo_candles),
        ]
        
        # Commodities: Twelve Data -> Yahoo
        self._commodity_providers = [
            ("twelvedata", self._get_twelvedata_candles),
            ("yahoo", self._get_yahoo_candles),
        ]
        
        self._providers_initialized = True
        logger.info("[router] providers initialized")
    
    def _get_bybit_candles(self, symbol: str, timeframe: str) -> List[Dict]:
        """Fetch crypto candles from Bybit via CCXT."""
        try:
            if self._connectors and hasattr(self._connectors, "bybit_get_candles"):
                return self._connectors.bybit_get_candles(symbol, timeframe) or []
        except Exception:
            pass
        
        # Fallback: direct bybit API call
        try:
            from data.fetcher import get_crypto_candles
            return get_crypto_candles(symbol, timeframe)
        except Exception:
            pass
        return []
    
    def _get_cryptocompare_candles(self, symbol: str, timeframe: str) -> List[Dict]:
        """Fetch crypto from CryptoCompare."""
        try:
            if self._legacy_providers and hasattr(self._legacy_providers, "fetch_coingecko_candles"):
                return self._legacy_providers.fetch_coingecko_candles(symbol, timeframe) or []
        except Exception:
            pass
        return []
    
    def _get_coingecko_candles(self, symbol: str, timeframe: str) -> List[Dict]:
        """Fetch from CoinGecko."""
        try:
            if self._legacy_providers and hasattr(self._legacy_providers, "fetch_coingecko_market_chart"):
                return self._legacy_providers.fetch_coingecko_market_chart(symbol) or []
        except Exception:
            pass
        return []
    
    def _get_polygon_candles(self, symbol: str, timeframe: str) -> List[Dict]:
        """Fetch from Polygon.io."""
        try:
            if self._legacy_providers and hasattr(self._legacy_providers, "fetch_polygon_candles"):
                return self._legacy_providers.fetch_polygon_candles(symbol, timeframe) or []
        except Exception:
            pass
        return []
    
    def _get_twelvedata_candles(self, symbol: str, timeframe: str) -> List[Dict]:
        """Fetch from Twelve Data."""
        try:
            if self._legacy_providers and hasattr(self._legacy_providers, "fetch_twelvedata_candles"):
                return self._legacy_providers.fetch_twelvedata_candles(symbol, timeframe) or []
        except Exception:
            pass
        return []
    
    def _get_oanda_candles(self, symbol: str, timeframe: str) -> List[Dict]:
        """Fetch from OANDA."""
        try:
            if self._legacy_providers and hasattr(self._legacy_providers, "fetch_oanda_candles"):
                return self._legacy_providers.fetch_oanda_candles(symbol, timeframe) or []
        except Exception:
            pass
        return []
    
    def _get_yahoo_candles(self, symbol: str, timeframe: str) -> List[Dict]:
        """Fetch from Yahoo Finance."""
        try:
            if self._legacy_providers and hasattr(self._legacy_providers, "fetch_yahoo_candles"):
                return self._legacy_providers.fetch_yahoo_candles(symbol, timeframe) or []
        except Exception:
            pass
        return []
    
    def _get_providers_for_asset_class(self, asset_class: str) -> List[tuple[str, callable]]:
        """Get provider list for asset class."""
        asset_class = (asset_class or "").lower().strip()
        
        if asset_class == "crypto":
            return self._crypto_providers
        elif asset_class == "fx" or asset_class == "forex":
            return self._fx_providers
        elif asset_class == "commodity":
            return self._commodity_providers
        else:
            return self._stock_providers
    
    async def fetch_price(self, symbol: str, asset_class: str) -> Optional[Dict]:
        """Fetch price data for symbol using appropriate provider.
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT", "EURUSD")
            asset_class: "crypto", "fx", "stock", or "commodity"
        
        Returns:
            Dictionary with price data or None if all providers fail
        """
        # Get timeframe from env or use default
        timeframe = os.getenv("DEFAULT_TIMEFRAME", "1h")
        
        providers = self._get_providers_for_asset_class(asset_class)
        
        # Try healthy providers first, then all providers
        healthy = [p for p in providers if _is_provider_healthy(p[0])]
        unhealthy = [p for p in providers if not _is_provider_healthy(p[0])]
        
        for provider_name, fetch_func in healthy + unhealthy:
            try:
                candles = fetch_func(symbol, timeframe)
                if candles and len(candles) >= 20:
                    _mark_provider_result(provider_name, True)
                    logger.info(
                        "[router] provider=%s symbol=%s class=%s candles=%d",
                        provider_name, symbol, asset_class, len(candles)
                    )
                    return {
                        "candles": candles,
                        "provider": provider_name,
                        "asset_class": asset_class,
                        "symbol": symbol,
                        "timeframe": timeframe,
                    }
                else:
                    _mark_provider_result(provider_name, False)
            except Exception as e:
                _mark_provider_result(provider_name, False)
                logger.warning(
                    "[router] provider=%s failed for %s: %s",
                    provider_name, symbol, e
                )
                continue
        
        logger.warning(
            "[router] all providers failed for symbol=%s class=%s",
            symbol, asset_class
        )
        return None
    
    async def fetch_with_fallback(self, symbol: str, asset_class: str) -> Optional[Dict]:
        """Fetch with explicit fallback chain - tries all providers in order."""
        from data.fetcher import get_candles as fetcher_get_candles
        
        # Use the existing multi-provider fetcher as primary
        try:
            candles = fetcher_get_candles(symbol, asset_class)
            if candles and len(candles) >= 20:
                return {
                    "candles": candles,
                    "provider": "fetcher_fallback",
                    "asset_class": asset_class,
                    "symbol": symbol,
                }
        except Exception as e:
            logger.warning("[router] fetcher fallback failed: %s", e)
        
        return None


# Global router instance
_router: Optional[DataRouter] = None


def get_router() -> DataRouter:
    """Get global router instance."""
    global _router
    if _router is None:
        _router = DataRouter()
    return _router


async def fetch_candles(symbol: str, asset_class: str) -> Optional[Dict]:
    """Convenience function to fetch candles via router."""
    router = get_router()
    return await router.fetch_price(symbol, asset_class)
