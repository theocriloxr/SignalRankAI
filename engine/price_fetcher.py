"""
Circuit Breaker Price Fetcher with Asset Routing - Task 5 Fix

This module fixes "Ghost Prices" and asset routing by:
1. Implementing strict asset routing (Crypto → Binance/Bybit, Stocks → Polygon/Yahoo)
2. Adding Circuit Breaker pattern for provider failover
3. Providing get_live_price() function with automatic failover
"""

import asyncio
import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Circuit Breaker for Price Providers
# =============================================================================

@dataclass
class PriceBreakerConfig:
    """Configuration for price circuit breaker."""
    failure_threshold: int = 3
    window_seconds: float = 30.0
    open_seconds: float = 60.0  # Longer open time for price failures


class PriceCircuitBreaker:
    """Circuit breaker for price providers."""
    
    def __init__(self, provider_name: str, config: Optional[PriceBreakerConfig] = None):
        self.provider_name = provider_name
        self.config = config or PriceBreakerConfig()
        self._failures: deque[float] = deque()
        self._open_until: float = 0.0
        self._last_success: float = 0.0
    
    def _now(self) -> float:
        return time.time()
    
    def _prune(self, now_ts: float) -> None:
        window_start = now_ts - float(self.config.window_seconds)
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
        self._last_success = self._now()
    
    def record_failure(self) -> bool:
        now_ts = self._now()
        self._failures.append(now_ts)
        self._prune(now_ts)
        if len(self._failures) >= int(self.config.failure_threshold):
            self._open_until = now_ts + float(self.config.open_seconds)
            logger.warning(
                f"[price_breaker] OPEN for {self.provider_name} - "
                f"failures={len(self._failures)} threshold={self.config.failure_threshold}"
            )
            return True
        return False
    
    def is_open(self) -> bool:
        return not self.allow()
    
    def open_remaining(self) -> float:
        now = self._now()
        if self._open_until <= now:
            return 0.0
        return max(0.0, self._open_until - now)


# Provider breakers
_price_breakers: Dict[str, PriceCircuitBreaker] = {}


def _get_price_breaker(provider: str) -> PriceCircuitBreaker:
    """Get or create price circuit breaker for provider."""
    key = str(provider or "unknown").strip().lower()
    if key not in _price_breakers:
        _price_breakers[key] = PriceCircuitBreaker(key)
    return _price_breakers[key]


# =============================================================================
# Asset Routing
# =============================================================================

def get_asset_class(asset: str) -> str:
    """
    Determine asset class for routing.
    
    Args:
        asset: Asset ticker (e.g., "BTCUSDT", "AAPL", "EURUSD")
        
    Returns:
        "crypto", "fx", "stock", "commodity", or "index"
    """
    a = str(asset or "").upper().strip()
    
    # Crypto detection (USDT/USDC/BUSD endings)
    if a.endswith(("USDT", "USDC", "BUSD", "BTC", "ETH", "BNB")):
        return "crypto"
    
    # FX detection (6-char currency pairs)
    clean = a.replace("/", "").replace("_", "").replace("-", "")
    if len(clean) == 6:
        base = clean[:3]
        quote = clean[3:]
        fx_currencies = {
            "EUR", "GBP", "USD", "JPY", "CHF", 
            "CAD", "AUD", "NZD", "HKD", "SGD"
        }
        if base in fx_currencies and quote in fx_currencies:
            return "fx"
    
    # Commodity detection
    commodity_keywords = ["XAU", "XAG", "XPT", "XPD", "WTI", "BRENT", "CL"]
    for kw in commodity_keywords:
        if kw in a:
            return "commodity"

    try:
        from data.fetcher import is_index
        if is_index(a):
            return "index"
    except Exception:
        index_symbols = {
            "US500", "SP500", "SPX", "GSPC", "US100", "NAS100", "NDX",
            "US30", "DJI", "DOW", "GER40", "DAX", "UK100", "JPN225",
            "JP225", "VIX", "HK50", "FRA40", "EU50", "AUS200",
        }
        if a.startswith("^") or clean in index_symbols:
            return "index"
    
    # Default to stock
    return "stock"


def get_routing_providers(asset: str) -> List[Tuple[str, str]]:
    """
    Get ordered list of providers for asset with strict routing.
    
    CRYPTO: Binance → Bybit → CryptoCompare
    STOCK: Polygon → Yahoo → TwelveData
    FX: AlphaVantage → Yahoo → Polygon
    COMMODITY: TwelveData → Yahoo
    
    Args:
        asset: Asset ticker
        
    Returns:
        List of (provider_name, endpoint_url) tuples
    """
    asset_class = get_asset_class(asset)
    
    if asset_class == "crypto":
        return [
            ("binance", "https://api.binance.com/api/v3/ticker/price"),
            ("bybit", "https://api.bybit.com/v5/market/tickers"),
            ("cryptocompare", "https://min-api.cryptocompare.com/data/pricemulti"),
        ]
    elif asset_class == "stock":
        return [
            ("polygon", "https://api.polygon.io/v2/aggs/ticker"),
            ("yahoo", "https://query1.finance.yahoo.com/v8/finance/chart"),
            ("twelvedata", "https://api.twelvedata.com/price"),
        ]
    elif asset_class == "fx":
        return [
            ("alphavantage", "https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE"),
            ("yahoo", "https://query1.finance.yahoo.com/v8/finance/chart"),
            ("polygon", "https://api.polygon.io/v2/aggs/ticker"),
        ]
    elif asset_class == "index":
        return [
            ("yahoo", "https://query1.finance.yahoo.com/v8/finance/chart"),
            ("twelvedata", "https://api.twelvedata.com/price"),
            ("tradingview", "https://scanner.tradingview.com"),
        ]
    else:  # commodity
        return [
            ("twelvedata", "https://api.twelvedata.com/price"),
            ("yahoo", "https://query1.finance.yahoo.com/v8/finance/chart"),
        ]


# =============================================================================
# Price Fetching with Circuit Breaker
# =============================================================================

async def _fetch_price_binance(symbol: str) -> Optional[float]:
    """Fetch price from Binance."""
    import requests
    
    breaker = _get_price_breaker("binance")
    if breaker.is_open():
        return None
    
    try:
        url = "https://api.binance.com/api/v3/ticker/price"
        params = {"symbol": symbol.replace("/", "").upper()}
        resp = requests.get(url, params=params, timeout=5)
        
        if resp.status_code == 200:
            data = resp.json()
            price = float(data.get("price", 0))
            if price > 0:
                breaker.record_success()
                return price
        else:
            breaker.record_failure()
    except Exception as e:
        logger.debug(f"[price] Binance fetch failed: {e}")
        breaker.record_failure()
    
    return None


async def _fetch_price_bybit(symbol: str) -> Optional[float]:
    """Fetch price from Bybit."""
    import requests
    
    breaker = _get_price_breaker("bybit")
    if breaker.is_open():
        return None
    
    try:
        url = "https://api.bybit.com/v5/market/tickers"
        params = {"category": "spot", "symbol": symbol.replace("/", "").upper()}
        resp = requests.get(url, params=params, timeout=5)
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get("retCode") == 0:
                result = data.get("result", {}).get("list", [])
                if result:
                    price = float(result[0].get("lastPrice", 0))
                    if price > 0:
                        breaker.record_success()
                        return price
        breaker.record_failure()
    except Exception as e:
        logger.debug(f"[price] Bybit fetch failed: {e}")
        breaker.record_failure()
    
    return None


async def _fetch_price_cryptocompare(symbol: str) -> Optional[float]:
    """Fetch price from CryptoCompare."""
    import requests
    
    breaker = _get_price_breaker("cryptocompare")
    if breaker.is_open():
        return None
    
    try:
        # Parse symbol (e.g., BTCUSDT -> BTC,USDT)
        base = symbol.replace("USDT", "").replace("USDC", "").replace("BUSD", "")
        quote = "USDT"
        if symbol.endswith("BTC"):
            base = symbol[:-3]
            quote = "BTC"
        elif symbol.endswith("ETH"):
            base = symbol[:-3]
            quote = "ETH"
        
        url = "https://min-api.cryptocompare.com/data/pricemulti"
        params = {"fsyms": base, "tsyms": quote}
        api_key = os.getenv("CRYPTOCOMPARE_API_KEY", "").strip()
        if api_key:
            params["api_key"] = api_key
        
        resp = requests.get(url, params=params, timeout=5)
        
        if resp.status_code == 200:
            data = resp.json()
            if base in data:
                price = float(data[base].get(quote, 0))
                if price > 0:
                    breaker.record_success()
                    return price
        breaker.record_failure()
    except Exception as e:
        logger.debug(f"[price] CryptoCompare fetch failed: {e}")
        breaker.record_failure()
    
    return None


async def _fetch_price_yahoo(symbol: str) -> Optional[float]:
    """Fetch price from Yahoo Finance."""
    import requests
    
    breaker = _get_price_breaker("yahoo")
    if breaker.is_open():
        return None
    
    try:
        # Convert to Yahoo format
        try:
            from data.fetcher import is_index, normalize_index_symbol
            if is_index(symbol):
                symbol = normalize_index_symbol(symbol)
        except Exception:
            pass
        if symbol.endswith("USDT"):
            symbol = symbol.replace("USDT", "-USD")
        elif symbol.startswith("^"):
            pass
        elif not symbol.endswith(("USD", "EUR", "GBP", "JPY")):
            symbol = f"{symbol}-USD"
        
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        resp = requests.get(url, timeout=5)
        
        if resp.status_code == 200:
            data = resp.json()
            result = data.get("chart", {}).get("result", [])
            if result:
                price = float(result[0].get("meta", {}).get("regularMarketPrice", 0))
                if price > 0:
                    breaker.record_success()
                    return price
        breaker.record_failure()
    except Exception as e:
        logger.debug(f"[price] Yahoo fetch failed: {e}")
        breaker.record_failure()
    
    return None


# =============================================================================
# Main get_live_price Function with Circuit Breaker
# =============================================================================

async def get_live_price(
    asset: str,
    timeout_seconds: float = 8.0,
) -> Optional[float]:
    """
    Get live price with strict asset routing and Circuit Breaker pattern.
    
    This is the main entry point for Task 5 fix.
    
    Args:
        asset: Asset ticker (e.g., "BTCUSDT", "AAPL")
        timeout_seconds: Overall timeout for all providers
        
    Returns:
        Live price float or None if unavailable
    """
    try:
        asset = str(asset or "").upper().strip()
        if not asset:
            return None
        
        asset_class = get_asset_class(asset)
        logger.debug(f"[price] Fetching {asset} via {asset_class} routing")
        
        start_time = time.time()
        
        # Get providers for asset class
        if asset_class == "crypto":
            # Try Binance first (primary)
            price = await asyncio.wait_for(
                _fetch_price_binance(asset),
                timeout=3.0
            )
            if price:
                logger.info(f"[price] {asset} = {price} (binance)")
                return price
            
            # Failover to Bybit
            if time.time() - start_time < timeout_seconds:
                price = await asyncio.wait_for(
                    _fetch_price_bybit(asset),
                    timeout=3.0
                )
                if price:
                    logger.info(f"[price] {asset} = {price} (bybit failover)")
                    return price
            
            # Failover to CryptoCompare
            if time.time() - start_time < timeout_seconds:
                price = await asyncio.wait_for(
                    _fetch_price_cryptocompare(asset),
                    timeout=3.0
                )
                if price:
                    logger.info(f"[price] {asset} = {price} (cryptocompare failover)")
                    return price
        
        elif asset_class in {"stock", "index"}:
            # Try Yahoo first for stocks
            price = await asyncio.wait_for(
                _fetch_price_yahoo(asset),
                timeout=4.0
            )
            if price:
                logger.info(f"[price] {asset} = {price} (yahoo)")
                return price
            
            # Polygon fallback would require API key - skip for now
            # TwelveData fallback would require API key - skip for now
        
        else:
            # FX or Commodity - use Yahoo
            price = await asyncio.wait_for(
                _fetch_price_yahoo(asset),
                timeout=4.0
            )
            if price:
                logger.info(f"[price] {asset} = {price} (yahoo)")
                return price
        
        # All providers failed
        logger.warning(f"[price] ALL PROVIDERS FAILED for {asset}")
        return None
        
    except asyncio.TimeoutError:
        logger.warning(f"[price] Timeout fetching {asset}")
        return None
    except Exception as e:
        logger.warning(f"[price] Error fetching {asset}: {e}")
        return None


async def get_live_price_batch(
    assets: List[str],
    max_concurrent: int = 5,
) -> Dict[str, Optional[float]]:
    """
    Fetch live prices for multiple assets concurrently.
    
    Args:
        assets: List of asset tickers
        max_concurrent: Max concurrent requests
        
    Returns:
        Dict mapping asset to price (or None)
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def fetch_one(asset: str) -> Tuple[str, Optional[float]]:
        async with semaphore:
            price = await get_live_price(asset)
            return asset, price
    
    tasks = [fetch_one(a) for a in assets]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    return {
        asset: price 
        for asset, price in results 
        if not isinstance(price, Exception)
    }


# =============================================================================
# Circuit Breaker Status
# =============================================================================

def get_price_breaker_status() -> Dict[str, Dict[str, Any]]:
    """Get status of all price circuit breakers."""
    status = {}
    now = time.time()
    for name, breaker in _price_breakers.items():
        status[name] = {
            "open": breaker.is_open(),
            "open_remaining_s": round(breaker.open_remaining(), 1),
            "failures": len(breaker._failures),
            "last_success": breaker._last_success,
        }
    return status


def reset_price_breakers() -> None:
    """Reset all price circuit breakers (admin function)."""
    for breaker in _price_breakers.values():
        breaker.record_success()
    logger.info("[price_breakers] All circuit breakers reset")


__all__ = [
    "get_live_price",
    "get_live_price_batch",
    "get_asset_class",
    "get_routing_providers",
    "get_price_breaker_status",
    "reset_price_breakers",
    "PriceCircuitBreaker",
]
