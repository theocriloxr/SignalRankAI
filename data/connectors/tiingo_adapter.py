"""
Tiingo Adapter - Premium Free Tier Provider

API Key required: TIINGO_API_KEY
Free Tier: 500 requests per hour
Best for: Stocks, Crypto, Forex

Docs: https://api.tiingo.com/docs/tiingo
"""
from __future__ import annotations

from typing import List, Dict, Any
import os
import logging

logger = logging.getLogger(__name__)

try:
    import httpx
except Exception:
    httpx = None

from utils.async_runner import run_sync
from utils import httpx_client


# Known crypto bases for detection
CRYPTO_BASES = {
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", 
    "LINK", "MATIC", "FIL", "APT", "NEAR", "ALGO", "ATOM", "UNI", "LTC",
    "BCH", "ETC", "XLM", "VET", "HBAR", "ALGB", "FTM", "SAND", "MANA",
}


async def _async_get_candles(
    symbol: str,
    timeframe: str,
    limit: int = 200,
    timeout: float = 10.0,
) -> List[Dict[str, Any]]:
    """
    Fetch candles from Tiingo API.
    
    Args:
        symbol: Trading symbol (e.g., "BTCUSDT", "AAPL")
        timeframe: Timeframe (1h, 4h, 1d) 
        limit: Number of candles to fetch
        timeout: Request timeout
        
    Returns:
        List of candle dicts with keys: timestamp, open, high, low, close, volume
    """
    api_key = (os.getenv("TIINGO_API_KEY") or "").strip()
    if not api_key:
        logger.debug("tiingo_adapter: TIINGO_API_KEY not set")
        return []

    # Determine asset type
    symbol = (symbol or "").upper().strip()
    symbol_clean = symbol.replace("/", "").replace("-", "").replace("_", "")
    
    # Check if crypto (ends with USDT/USB or base is crypto)
    is_crypto = (
        symbol_clean.endswith("USDT") or 
        symbol_clean.endswith("USD") or 
        any(symbol_clean.startswith(b) for b in CRYPTO_BASES)
    )
    
    request_timeout = min(10.0, max(2.0, float(timeout)))
    
    try:
        if is_crypto:
            # Crypto endpoint: https://api.tiingo.com/tiingo/crypto/prices
            # Format: BTCUSDT -> btcusd (lowercase)
            base = symbol_clean[:-4] if symbol_clean.endswith("USDT") else symbol_clean[:-3]
            tiingo_symbol = f"{base.lower()}usd"
            
            # Map timeframe for crypto
            tf_map = {
                "1m": "1min",
                "5m": "5min",
                "15m": "15min", 
                "1h": "1hour",
                "4h": "4hour",
                "1d": "1day"
            }
            resample_tf = tf_map.get((timeframe or "").strip().lower(), "1hour")
            
            url = (
                f"https://api.tiingo.com/tiingo/crypto/prices?"
                f"tickers={tiingo_symbol}&"
                f"resampleFreq={resample_tf}&"
                f"token={api_key}"
            )
        else:
            # Stock/Forex endpoint: https://api.tiingo.com/tiingo/daily/{symbol}/prices
            stock_symbol = symbol.lower()
            url = (
                f"https://api.tiingo.com/tiingo/daily/{stock_symbol}/prices?"
                f"token={api_key}"
            )
        
        client = httpx_client.get_client("tiingo")
        
        if client is not None:
            resp = await client.get(url, timeout=request_timeout)
        else:
            async with httpx.AsyncClient(timeout=request_timeout) as client_fallback:
                resp = await client_fallback.get(url)
        
        if resp.status_code != 200:
            logger.debug(f"tiingo_adapter HTTP {resp.status_code}: {getattr(resp, 'text', '')[:200]}")
            return []
        
        data = resp.json()
        
        if not data or not isinstance(data, list):
            return []
        
        out: List[Dict[str, Any]] = []
        
        if is_crypto:
            # Crypto returns: [{"ticker": "...", "priceData": [...]}]
            price_data = data[0].get("priceData", []) if data else []
            for row in price_data[:limit]:
                try:
                    # Row format per Tiingo docs
                    out.append({
                        "timestamp": row.get("date"),
                        "open": float(row.get("open", 0)),
                        "high": float(row.get("high", 0)),
                        "low": float(row.get("low", 0)),
                        "close": float(row.get("close", 0)),
                        "volume": float(row.get("volume", 0)),
                    })
                except (ValueError, TypeError) as e:
                    logger.debug(f"tiingo_adapter parse error: {e}")
                    continue
        else:
            # Stocks/Forex returns: [{date, open, high, low, close, volume}, ...]
            for row in data[:limit]:
                try:
                    out.append({
                        "timestamp": row.get("date"),
                        "open": float(row.get("open", 0)),
                        "high": float(row.get("high", 0)),
                        "low": float(row.get("low", 0)),
                        "close": float(row.get("close", 0)),
                        "volume": float(row.get("volume", 0)),
                    })
                except (ValueError, TypeError) as e:
                    logger.debug(f"tiingo_adapter parse error: {e}")
                    continue
        
        # Tiingo returns chronological order (oldest first)
        return out
        
    except Exception as e:
        logger.debug(f"tiingo_adapter exception: {e}")
        return []


def get_candles(
    symbol: str,
    timeframe: str,
    limit: int = 200,
    timeout: float = 10.0,
) -> List[Dict[str, Any]]:
    """
    Sync-compatible wrapper that runs the async Tiingo client safely.
    """
    return run_sync(
        _async_get_candles(symbol, timeframe, limit=limit, timeout=timeout)
    )
