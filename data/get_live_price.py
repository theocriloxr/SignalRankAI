"""
Live Price Fetcher with Circuit Breaker - Task 5 Fix

This module:
- Implements strict asset routing: Crypto (USDT/*) → Binance/Bybit, Stocks → Yahoo
- Uses Circuit Breaker pattern for each provider
- Provides automatic failover on rate limits/geo-blocks
- Prevents "Ghost Price" from wrong provider
"""

import os
import logging
import asyncio
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from collections import deque
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ============================================================================
# Circuit Breaker Configuration
# ============================================================================

@dataclass
class PriceCircuitConfig:
    """Configuration for price circuit breaker."""
    failure_threshold: int = 3  # Open after 3 failures
    window_seconds: float = 60.0  # Track failures in 60s window
    open_seconds: float = 30.0  # Stay open for 30s


class PriceCircuitBreaker:
    """Circuit breaker for price providers."""
    
    def __init__(self, config: Optional[PriceCircuitConfig] = None):
        self.config = config or PriceCircuitConfig()
        self._failures: deque[float] = deque()
        self._open_until: float = 0.0
    
    def _now(self) -> float:
        return time.time()
    
    def _prune(self, now_ts: float) -> None:
        window_start = now_ts - self.config.window_seconds
        while self._failures and self._failures[0] < window_start:
            self._failures.popleft()
    
    def allow(self) -> bool:
        now_ts = self._now()
        if now_ts < self._open_until:
            return False
        self._prune(now_ts)
        return True
    
    def record_success(self) -> None:
        self._failures.clear()
        self._open_until = 0.0
    
    def record_failure(self) -> bool:
        now_ts = self._now()
        self._failures.append(now_ts)
        self._prune(now_ts)
        
        if len(self._failures) >= self.config.failure_threshold:
            self._open_until = now_ts + self.config.open_seconds
            return True
        return False


# Provider circuit breakers
_price_breakers: Dict[str, PriceCircuitBreaker] = {}


def _get_breaker(provider: str) -> PriceCircuitBreaker:
    """Get or create circuit breaker for provider."""
    if provider not in _price_breakers:
        _price_breakers[provider] = PriceCircuitBreaker()
    return _price_breakers[provider]


# ============================================================================
# Asset Routing Logic
# ============================================================================

def _is_crypto(asset: str) -> bool:
    """Check if asset is crypto (USDT, USDC, BUSD, etc.)."""
    a = (asset or "").upper().strip()
    return (
        a.endswith("USDT") or 
        a.endswith("USDC") or 
        a.endswith("BUSD") or
        a.endswith("BTC") or
        a.endswith("ETH")
    )


def _get_providers_for_asset(asset: str) -> List[str]:
    """
    Get provider priority list for asset.
    
    Strict routing:
    - Crypto (USDT/*) → Binance → Bybit → CryptoCompare
    - Stocks → Yahoo → Polygon
    """
    if _is_crypto(asset):
        return ["binance", "bybit", "cryptocompare"]
    else:
        # Stocks and other assets
        return ["yahoo", "polygon"]


# ============================================================================
# Price Fetching Functions
# ============================================================================

async def _fetch_binance_price(symbol: str) -> Optional[float]:
    """Fetch price from Binance public API."""
    import requests
    
    breaker = _get_breaker("binance")
    if not breaker.allow():
        return None
    
    try:
        sym = symbol.upper().replace("/", "").replace("-", "")
        if not sym.endswith("USDT") and not sym.endswith("USDC"):
            sym += "USDT"
        
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={sym}"
        resp = requests.get(url, timeout=5)
        
        if resp.ok:
            data = resp.json()
            price = data.get("price")
            if price:
                breaker.record_success()
                return float(price)
        
        breaker.record_failure()
        return None
        
    except Exception as e:
        breaker.record_failure()
        logger.debug(f"[price] Binance error for {symbol}: {e}")
        return None


async def _fetch_bybit_price(symbol: str) -> Optional[float]:
    """Fetch price from Bybit public API."""
    import requests
    
    breaker = _get_breaker("bybit")
    if not breaker.allow():
        return None
    
    try:
        sym = symbol.upper().replace("/", "").replace("-", "")
        
        url = "https://api.bybit.com/v5/market/ticker"
        params = {
            "category": "spot",
            "symbol": sym,
        }
        
        resp = requests.get(url, params=params, timeout=5)
        
        if resp.ok:
            data = resp.json()
            if str(data.get("retCode", "1")) == "0":
                result = data.get("result", {})
                price = result.get("lastPrice")
                if price:
                    breaker.record_success()
                    return float(price)
        
        breaker.record_failure()
        return None
        
    except Exception as e:
        breaker.record_failure()
        logger.debug(f"[price] Bybit error for {symbol}: {e}")
        return None


async def _fetch_cryptocompare_price(symbol: str) -> Optional[float]:
    """Fetch price from CryptoCompare."""
    import requests
    
    breaker = _get_breaker("cryptocompare")
    if not breaker.allow():
        return None
    
    try:
        # Parse symbol (BTCUSDT -> BTC,USDT)
        sym = symbol.upper().replace("/", "").replace("-", "")
        base = sym
        quote = "USDT"
        
        for q in ("USDT", "USDC", "BUSD", "USD"):
            if sym.endswith(q):
                base = sym[:-len(q)]
                quote = q
                break
        
        api_key = os.getenv("CRYPTOCOMPARE_API_KEY", "").strip()
        
        url = "https://min-api.cryptocompare.com/data/price"
        params = {
            "fsym": base,
            "tsyms": quote,
        }
        if api_key:
            params["api_key"] = api_key
        
        resp = requests.get(url, params=params, timeout=5)
        
        if resp.ok:
            data = resp.json()
            price = data.get(quote)
            if price:
                breaker.record_success()
                return float(price)
        
        breaker.record_failure()
        return None
        
    except Exception as e:
        breaker.record_failure()
        logger.debug(f"[price] CryptoCompare error for {symbol}: {e}")
        return None


async def _fetch_yahoo_price(symbol: str) -> Optional[float]:
    """Fetch price from Yahoo Finance."""
    import requests
    
    breaker = _get_breaker("yahoo")
    if not breaker.allow():
        return None
    
    try:
        # Yahoo format: BTC-USD -> BTCUSD=X
        sym = symbol.upper().replace("/", "-")
        if not sym.endswith("=X") and not sym.endswith("USD"):
            if not sym.endswith("=X"):
                sym = f"{sym}=X"
        
        url = f"https://query1.finance.yahoo.com/v8/finance/charts/{sym}"
        resp = requests.get(url, timeout=5)
        
        if resp.ok:
            data = resp.json()
            chart = data.get("chart", {})
            result = chart.get("result", [])
            if result:
                meta = result[0].get("meta", {})
                price = meta.get("regularMarketPrice")
                if price:
                    breaker.record_success()
                    return float(price)
        
        breaker.record_failure()
        return None
        
    except Exception as e:
        breaker.record_failure()
        logger.debug(f"[price] Yahoo error for {symbol}: {e}")
        return None


async def _fetch_polygon_price(symbol: str) -> Optional[float]:
    """Fetch price from Polygon.io."""
    import requests
    
    breaker = _get_breaker("polygon")
    if not breaker.allow():
        return None
    
    try:
        api_key = os.getenv("POLYGON_API_KEY", "").strip()
        if not api_key:
            return None
        
        # Clean symbol
        sym = symbol.upper().replace("/", "").replace("-", "")
        
        url = f"https://api.polygon.io/v2/aggs/ticker/{sym}/prev"
        params = {"apiKey": api_key}
        
        resp = requests.get(url, params=params, timeout=5)
        
        if resp.ok:
            data = resp.json()
            results = data.get("results", [])
            if results:
                price = results[0].get("c")  # Close price
                if price:
                    breaker.record_success()
                    return float(price)
        
        breaker.record_failure()
        return None
        
    except Exception as e:
        breaker.record_failure()
        logger.debug(f"[price] Polygon error for {symbol}: {e}")
        return None


# ============================================================================
# Primary API with Circuit Breaker & Failover
# ============================================================================

async def get_live_price(
    symbol: str,
    timeout: float = 5.0,
) -> Optional[float]:
    """
    Get live price with circuit breaker and automatic failover.
    
    This is the MAIN entry point - replaces all direct price fetches.
    
    Features:
    - Strict asset routing (crypto vs stocks)
    - Circuit breaker per provider
    - Automatic failover on rate limits
    - Prevents "Ghost Price" from wrong provider
    
    Args:
        symbol: Asset symbol (e.g., "BTCUSDT", "AAPL")
        timeout: Maximum wait time in seconds
        
    Returns:
        Live price or None if unavailable
    """
    if not symbol:
        return None
    
    symbol = symbol.upper().strip()
    
    # Get provider priority for asset type
    providers = _get_providers_for_asset(symbol)
    
    # Try each provider with circuit breaker
    for provider in providers:
        try:
            price = None
            
            if provider == "binance":
                price = await asyncio.wait_for(
                    _fetch_binance_price(symbol),
                    timeout=timeout,
                )
            elif provider == "bybit":
                price = await asyncio.wait_for(
                    _fetch_bybit_price(symbol),
                    timeout=timeout,
                )
            elif provider == "cryptocompare":
                price = await asyncio.wait_for(
                    _fetch_cryptocompare_price(symbol),
                    timeout=timeout,
                )
            elif provider == "yahoo":
                price = await asyncio.wait_for(
                    _fetch_yahoo_price(symbol),
                    timeout=timeout,
                )
            elif provider == "polygon":
                price = await asyncio.wait_for(
                    _fetch_polygon_price(symbol),
                    timeout=timeout,
                )
            
            if price and price > 0:
                logger.info(
                    f"[price] {symbol}: {price} (provider={provider})"
                )
                return price
            
            # Provider failed or returned invalid price - continue to next
            logger.debug(
                f"[price] {symbol}: provider={provider} failed/invalid, "
                f"trying next..."
            )
            
        except asyncio.TimeoutError:
            logger.debug(f"[price] {symbol}: {provider} timeout")
            continue
        except Exception as e:
            logger.debug(f"[price] {symbol}: {provider} error: {e}")
            continue
    
    # All providers failed
    logger.warning(f"[price] All providers failed for {symbol}")
    return None


async def get_cached_price(
    symbol: str,
    max_age_seconds: float = 30.0,
) -> Optional[float]:
    """
    Get price with optional cache.
    
    Uses Redis cache if available to reduce API calls.
    """
    try:
        from core.redis_state import state
        
        cache_key = f"live_price:{symbol.upper()}"
        
        # Try cache first
        cached = await state.cache_get(cache_key)
        if cached:
            import json
            try:
                data = json.loads(cached)
                price = data.get("price")
                ts = data.get("timestamp", 0)
                
                if price and ts:
                    age = time.time() - ts
                    if age <= max_age_seconds:
                        return float(price)
            except Exception:
                pass
        
        # Fetch fresh price
        price = await get_live_price(symbol)
        
        if price:
            # Cache it
            import json
            await state.cache_set(
                cache_key,
                json.dumps({"price": price, "timestamp": time.time()}),
                ex=int(max_age_seconds),
            )
        
        return price
        
    except Exception as e:
        logger.debug(f"[price] Cache error: {e}")
        return await get_live_price(symbol)


# Convenience function aliases
get_price = get_live_price
fetch_price = get_live_price


# ============================================================================
# Diagnostic Functions
# ============================================================================

def get_circuit_breaker_status() -> Dict[str, Dict[str, Any]]:
    """Get circuit breaker status for all providers."""
    status = {}
    
    for name, breaker in _price_breakers.items():
        now = time.time()
        open_remaining = max(0.0, breaker._open_until - now) if breaker._open_until else 0.0
        
        status[name] = {
            "open": bool(open_remaining > 0),
            "open_remaining_s": open_remaining,
            "failures": len(breaker._failures),
        }
    
    return status


__all__ = [
    "get_live_price",
    "get_cached_price",
    "get_price",
    "fetch_price",
    "get_circuit_breaker_status",
    "_is_crypto",
    "_get_providers_for_asset",
]
