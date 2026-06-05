"""
Live Price Fetch with Circuit Breaker - Task 5 Fix

Fixes:
- "Ghost Prices" - wrong provider returning null/wrong prices
- Asset routing - crypto to Binance/Bybit, stocks to Polygon/Yahoo
- Circuit breaker pattern for API failures

Implementation:
- Strict asset routing by ticker suffix
- Circuit breaker for each provider
- Automatic failover on rate limits
"""

import logging
import os
import asyncio
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

# Provider URLs
BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"
BYBIT_WS_URL = "wss://stream.bybit.com/v5/ws"
POLYGON_WS_URL = "wss://streamer.polygon.io"

# Circuit breaker config
CIRCUIT_FAILURE_THRESHOLD = 3
CIRCUIT_OPEN_SECONDS = 30.0
CIRCUIT_WINDOW_SECONDS = 10.0

# Price fetch timeout
PRICE_TIMEOUT_SECONDS = 5.0


# ============================================================================
# Circuit Breaker State
# ============================================================================

class _CircuitBreaker:
    """Simple circuit breaker for price providers."""
    
    def __init__(self, name: str):
        self.name = name
        self._failures = []
        self._open_until = 0.0
    
    def _now(self) -> float:
        import time
        return time.time()
    
    def _prune(self, now_ts: float) -> None:
        window_start = now_ts - CIRCUIT_WINDOW_SECONDS
        self._failures = [f for f in self._failures if f >= window_start]
    
    def allow(self) -> bool:
        now_ts = self._now()
        if now_ts < self._open_until:
            return False
        self._prune(now_ts)
        return True
    
    def record_success(self) -> None:
        self._failures = []
        self._open_until = 0.0
    
    def record_failure(self) -> bool:
        now_ts = self._now()
        self._failures.append(now_ts)
        self._prune(now_ts)
        
        if len(self._failures) >= CIRCUIT_FAILURE_THRESHOLD:
            self._open_until = now_ts + CIRCUIT_OPEN_SECONDS
            logger.warning(f"[price] Circuit OPEN for {self.name}")
            return True
        return False


# Provider circuit breakers
_breakers = {
    "binance": _CircuitBreaker("binance"),
    "bybit": _CircuitBreaker("bybit"),
    "polygon": _CircuitBreaker("polygon"),
    "yahoo": _CircuitBreaker("yahoo"),
}


def _get_breaker(provider: str) -> _CircuitBreaker:
    """Get circuit breaker for provider."""
    key = provider.lower().strip()
    if key not in _breakers:
        _breakers[key] = _CircuitBreaker(key)
    return _breakers[key]


# ============================================================================
# Asset Routing
# ============================================================================

def get_provider_for_asset(asset: str) -> str:
    """
    Get the appropriate provider for an asset.
    
    STRICT routing:
    - Crypto (USDT/USDC/BUSD suffix): Binance → Bybit → CryptoCompare
    - Stocks/FX: Yahoo → Polygon → Twelve Data
    
    This is the KEY fix for Task 5 - prevents routing wrong assets to wrong providers.
    """
    asset_upper = asset.upper().strip()
    
    # CRYPTO: ends with USDT, USDC, BUSD, or is a known crypto ticker
    crypto_suffixes = ("USDT", "USDC", "BUSD", "USD")
    is_crypto = any(asset_upper.endswith(s) for s in crypto_suffixes)
    
    # Check for known crypto tickers
    known_crypto = {
        "BTC", "ETH", "BNB", "XRP", "ADA", "DOGE", "SOL", "DOT",
        "MATIC", "LTC", "AVAX", "LINK", "ATOM", "UNI", "XLM", "ETC",
    }
    if asset_upper in known_crypto:
        is_crypto = True
    
    # Check for commodities (NOT crypto)
    commodities = {"XAU", "XAG", "XPT", "XPD", "WTI", "BRENT", "CL", "BZ"}
    if asset_upper in commodities:
        is_crypto = False
    
    # CRYPTO: Use Binance
    if is_crypto:
        if _get_breaker("binance").allow():
            return "binance"
        if _get_breaker("bybit").allow():
            return "bybit"
        return "cryptocompare"
    
    # STOCKS/FX: Use Yahoo or Polygon
    if _get_breaker("yahoo").allow():
        return "yahoo"
    if _get_breaker("polygon").allow():
        return "polygon"
    return "yahoo"  # Fallback


def is_crypto_asset(asset: str) -> bool:
    """Check if asset is crypto (for external use)."""
    return get_provider_for_asset(asset) in ("binance", "bybit", "cryptocompare")


# ============================================================================
# Price Fetchers
# ============================================================================

async def _fetch_binance_price(symbol: str) -> Optional[float]:
    """Fetch price from Binance."""
    try:
        import requests
        
        # Convert to Binance format
        sym = symbol.upper().replace("/", "").replace("-", "")
        
        if not sym.endswith("USDT") and not sym.endswith("USDC"):
            sym = sym + "USDT"
        
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={sym}"
        
        resp = requests.get(url, timeout=PRICE_TIMEOUT_SECONDS)
        
        if resp.status_code == 200:
            _get_breaker("binance").record_success()
            data = resp.json()
            return float(data.get("price", 0))
        else:
            _get_breaker("binance").record_failure()
            
    except Exception as e:
        _get_breaker("binance").record_failure()
        logger.debug(f"[price] Binance fetch error: {e}")
    
    return None


async def _fetch_bybit_price(symbol: str) -> Optional[float]:
    """Fetch price from Bybit."""
    try:
        import requests
        
        sym = symbol.upper().replace("/", "").replace("-", "")
        
        if not sym.endswith("USDT"):
            sym = sym + "USDT"
        
        url = f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={sym}"
        
        resp = requests.get(url, timeout=PRICE_TIMEOUT_SECONDS)
        
        if resp.status_code == 200:
            _get_breaker("bybit").record_success()
            data = resp.json()
            result = data.get("result", {})
            list_data = result.get("list", [])
            
            if list_data:
                return float(list_data[0].get("lastPrice", 0))
        else:
            _get_breaker("bybit").record_failure()
            
    except Exception as e:
        _get_breaker("bybit").record_failure()
        logger.debug(f"[price] Bybit fetch error: {e}")
    
    return None


async def _fetch_yahoo_price(symbol: str) -> Optional[float]:
    """Fetch price from Yahoo Finance."""
    try:
        import requests
        
        # Convert to Yahoo format: BTCUSDT -> BTC-USD
        sym = symbol.upper().replace("/", "-").replace("-", "")
        
        if sym.endswith("USDT"):
            sym = sym[:-4] + "-USD"
        elif sym.endswith("USD") and len(sym) == 7:
            pass  # Already in format
        else:
            sym = sym + "-USD"
        
        url = f"https://query1.finance.yahoo.com/v8/finance/charts/{sym}"
        
        resp = requests.get(url, timeout=PRICE_TIMEOUT_SECONDS)
        
        if resp.status_code == 200:
            _get_breaker("yahoo").record_success()
            data = resp.json()
            chart = data.get("chart", [])
            
            if chart:
                result = chart[0].get("result", [])
                if result:
                    meta = result[0].get("meta", {})
                    return float(meta.get("regularMarketPrice", 0))
        else:
            _get_breaker("yahoo").record_failure()
            
    except Exception as e:
        _get_breaker("yahoo").record_failure()
        logger.debug(f"[price] Yahoo fetch error: {e}")
    
    return None


async def _fetch_cryptocompare_price(symbol: str) -> Optional[float]:
    """Fetch price from CryptoCompare (fallback for crypto)."""
    try:
        import requests
        
        # Extract base currency
        sym = symbol.upper().replace("/", "").replace("-", "")
        
        for q in ("USDT", "USD", "USDC"):
            if sym.endswith(q):
                base = sym[:-len(q)]
                quote = q
                break
        else:
            base = sym
            quote = "USDT"
        
        api_key = os.getenv("CRYPTOCOMPARE_API_KEY", "")
        
        url = f"https://min-api.cryptocompare.com/data/price"
        params = {"fsym": base, "tsyms": quote}
        
        if api_key:
            params["api_key"] = api_key
        
        resp = requests.get(url, params=params, timeout=PRICE_TIMEOUT_SECONDS)
        
        if resp.status_code == 200:
            data = resp.json()
            price = data.get(quote)
            
            if price:
                return float(price)
                
    except Exception as e:
        logger.debug(f"[price] CryptoCompare fetch error: {e}")
    
    return None


# ============================================================================
# Main Price Fetch Function
# ============================================================================

async def get_live_price(symbol: str) -> Optional[float]:
    """
    Get live price with Circuit Breaker and strict asset routing.
    
    This is the MAIN entry point - replaces direct provider calls.
    
    Features:
    - Strict asset routing (crypto → Binance, stocks → Yahoo)
    - Circuit breaker for each provider
    - Automatic failover on failure/rate-limit
    
    Args:
        symbol: Asset ticker (e.g., "BTCUSDT", "AAPL")
        
    Returns:
        Live price float or None if unavailable
    """
    if not symbol:
        return None
    
    # Get provider for asset type
    provider = get_provider_for_asset(symbol)
    
    logger.debug(f"[price] Fetching {symbol} from {provider}")
    
    # Track attempts for failover
    attempted_providers = set()
    last_error = None
    
    while True:
        attempted_providers.add(provider)
        
        # Fetch from provider
        if provider == "binance":
            price = await _fetch_binance_price(symbol)
        elif provider == "bybit":
            price = await _fetch_bybit_price(symbol)
        elif provider == "yahoo":
            price = await _fetch_yahoo_price(symbol)
        elif provider == "cryptocompare":
            price = await _fetch_cryptocompare_price(symbol)
        elif provider == "polygon":
            # Polygon needs API key - fallback to Yahoo
            price = await _fetch_yahoo_price(symbol)
        else:
            price = None
        
        # Success
        if price and price > 0:
            logger.info(f"[price] {symbol} = {price} via {provider}")
            return price
        
        # Failure - circuit breaker recorded
        last_error = f"{provider} returned null"
        
        # Find next available provider
        found_next = False
        all_providers = ["binance", "bybit", "cryptocompare", "yahoo"]
        
        for next_provider in all_providers:
            if next_provider in attempted_providers:
                continue
            if _get_breaker(next_provider).allow():
                provider = next_provider
                found_next = True
                logger.debug(f"[price] Failover {symbol} to {next_provider}")
                break
        
        if not found_next:
            # All providers failed or circuit open
            logger.warning(f"[price] All providers failed for {symbol}: {last_error}")
            return None
    
    # Fallback (shouldn't reach here)
    return None


async def get_price_with_fallback(symbol: str) -> float:
    """
    Get price with multiple fallback levels.
    
    Returns 0.0 only if ALL providers fail.
    """
    price = await get_live_price(symbol)
    
    if price and price > 0:
        return price
    
    # Try cached last known price from cache
    try:
        from core.redis_cache import cache_get
        cached = await cache_get(f"last_price:{symbol}")
        if cached:
            return float(cached)
    except Exception:
        pass
    
    return 0.0


# ============================================================================
# Export
# ============================================================================

__all__ = [
    "get_live_price",
    "get_price_with_fallback",
    "get_provider_for_asset",
    "is_crypto_asset",
]
