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
import traceback
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
        
# ==============================================================
        # MULTI-PROVIDER FALLBACK CHAINS (STARVATION_FIX_V5)
        # Priority: Direct exchanges -> Free tier APIs -> yfinance safety net
        # 
        # CRITICAL FIX: Geo-blocking bypass for Railway/Nigeria users
        # - Binance is blocked in some regions (Railway)
        # - Bybit works when Binance is blocked
        # - CryptoCompare works worldwide as last resort
        # ==============================================================
        
        # Crypto: Bybit -> Binance -> KuCoin -> CryptoCompare -> CoinGecko -> yfinance
        # Order matters: Bybit first (often works when Binance blocked)
        # Binance second (try first on non-blocked infrastructure)
        self._crypto_providers = [
            ("bybit", self._get_bybit_candles),      # PRIMARY - works when Binance blocked
            ("binance", self._get_binance_candles),   # Secondary - works on normal infra
            ("kucoin", self._get_kucoin_candles),      # NO API KEY - free
            ("cryptocompare", self._get_cryptocompare_candles),
            ("coingecko", self._get_coingecko_candles),  # Free - works worldwide
            ("yahoo", self._get_yahoo_candles),      # Safety net
        ]
        
        # Stocks: Tiingo -> Twelve Data -> FMP -> yfinance
        # - Tiingo: Free tier 500 req/hr, best for stocks
        # - Twelve Data: Free tier 800/day, key in TWELVEDATA_API_KEY
        # - FMP: Free tier 250/day, key in FMP_API_KEY
        self._stock_providers = [
            ("tiingo", self._get_tiingo_candles),
            ("twelvedata", self._get_twelvedata_candles),
            ("fmp", self._get_fmp_candles),
            ("yahoo", self._get_yahoo_candles),
        ]
        
        # Forex: Twelve Data -> Tiingo -> FCS -> yfinance
        # - Twelve Data: Best for Forex pairs
        # - FCS: fcsapi.com key in FCS_API_KEY
        self._fx_providers = [
            ("twelvedata", self._get_twelvedata_candles),
            ("tiingo", self._get_tiingo_candles),
            ("fcs", self._get_fcs_candles),
            ("yahoo", self._get_yahoo_candles),
        ]
        
        # Commodities: Twelve Data -> Tiingo -> yfinance
        self._commodity_providers = [
            ("twelvedata", self._get_twelvedata_candles),
            ("tiingo", self._get_tiingo_candles),
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
    
    def _get_binance_candles(self, symbol: str, timeframe: str) -> List[Dict]:
        """Fetch crypto candles from Binance REST API."""
        try:
            from data.connectors.binance_adapter import get_candles as binance_get_candles
            return binance_get_candles(symbol, timeframe) or []
        except Exception as e:
            logger.error("❌ FATAL CRASH in binance adapter for %s!", symbol)
            logger.error(traceback.format_exc())
            return []
        
    def _get_kucoin_candles(self, symbol: str, timeframe: str) -> List[Dict]:
        """Fetch from KuCoin (NO API KEY - free crypto)."""
        try:
            from data.connectors.kucoin_adapter import get_candles as kucoin_get_candles
            return kucoin_get_candles(symbol, timeframe) or []
        except Exception as e:
            logger.error("❌ FATAL CRASH in kucoin adapter for %s!", symbol)
            logger.error(traceback.format_exc())
            return []
        
    
    def _get_tiingo_candles(self, symbol: str, timeframe: str) -> List[Dict]:
        """Fetch from Tiingo (requires TIINGO_API_KEY)."""
        try:
            from data.connectors.tiingo_adapter import get_candles as tiingo_get_candles
            return tiingo_get_candles(symbol, timeframe) or []
        except Exception as e:
            logger.error("❌ FATAL CRASH in tiingo adapter for %s!", symbol)
            logger.error(traceback.format_exc())
            return []
        
    
    def _get_fmp_candles(self, symbol: str, timeframe: str) -> List[Dict]:
        """Fetch from Financial Modeling Prep (requires FMP_API_KEY)."""
        try:
            from data.connectors.fmp_adapter import get_candles as fmp_get_candles
            return fmp_get_candles(symbol, timeframe) or []
        except Exception as e:
            logger.error("❌ FATAL CRASH in fmp adapter for %s!", symbol)
            logger.error(traceback.format_exc())
            return []
      
    
    def _get_fcs_candles(self, symbol: str, timeframe: str) -> List[Dict]:
        """Fetch from FCS API (requires FCS_API_KEY)."""
        try:
            from data.connectors.fcs_adapter import get_candles as fcs_get_candles
            return fcs_get_candles(symbol, timeframe) or []
        except Exception as e:
            logger.error("❌ FATAL CRASH in fcs adapter for %s!", symbol)
            logger.error(traceback.format_exc())
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
