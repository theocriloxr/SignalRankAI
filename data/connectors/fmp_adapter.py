"""
FMP Adapter - Financial Modeling Prep (Stocks)

API Key required: FMP_API_KEY
Free Tier: 250 requests per day
Best for: Stocks, ETFs, Forex (NOT crypto)

Docs: https://site.financialmodelingprep.com/developer/docs
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


async def _async_get_candles(
    symbol: str,
    timeframe: str,
    limit: int = 200,
    timeout: float = 10.0,
) -> List[Dict[str, Any]]:
    """
    Fetch candles from FMP API.
    
    Args:
        symbol: Trading symbol (e.g., "AAPL", "EURUSD")
        timeframe: Timeframe (1h, 4h, 1d) 
        limit: Number of candles to fetch
        timeout: Request timeout
        
    Returns:
        List of candle dicts with keys: timestamp, open, high, low, close, volume
    """
    api_key = (os.getenv("FMP_API_KEY") or "").strip()
    if not api_key:
        logger.debug("fmp_adapter: FMP_API_KEY not set")
        return []

    # Clean symbol
    symbol = (symbol or "").upper().strip()
    symbol_clean = symbol.replace("/", "").replace("-", "").replace("_", "")
    
    request_timeout = min(10.0, max(2.0, float(timeout)))
    
    # Map timeframe to FMP format
    tf_map = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min", 
        "1h": "1hour",
        "4h": "4hour",
        "1d": "1day"  # FMP uses 1day for daily
    }
    fmp_tf = tf_map.get((timeframe or "").strip().lower(), "1hour")
    
    try:
        # FMP historical candles endpoint
        url = (
            f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol_clean}?"
            f"from=2020-01-01&"
            f"to=2030-01-01&"
            f"timeseries={fmp_tf}&"
            f"apikey={api_key}"
        )
        
        client = httpx_client.get_client("fmp")
        
        if client is not None:
            resp = await client.get(url, timeout=request_timeout)
        else:
            async with httpx.AsyncClient(timeout=request_timeout) as client_fallback:
                resp = await client_fallback.get(url)
        
        if resp.status_code != 200:
            logger.debug(f"fmp_adapter HTTP {resp.status_code}: {getattr(resp, 'text', '')[:200]}")
            return []
        
        data = resp.json()
        
        # FMP returns: {"symbol": "AAPL", "historical": [...]}
        if not data or not isinstance(data, dict):
            return []
        
        # Check for API error messages
        if "Error" in str(data):
            logger.debug(f"fmp_adapter API error: {data}")
            return []
        
        historical = data.get("historical")
        if not historical or not isinstance(historical, list):
            return []
        
        out: List[Dict[str, Any]] = []
        
        for row in historical[:limit]:
            try:
                # FMP historical format
                out.append({
                    "timestamp": row.get("date"),
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "close": float(row.get("close", 0)),
                    "volume": float(row.get("volume", 0)),
                })
            except (ValueError, TypeError) as e:
                logger.debug(f"fmp_adapter parse error: {e}")
                continue
        
        # FMP returns reverse chronological, so reverse to get oldest first
        return out[::-1]
        
    except Exception as e:
        logger.debug(f"fmp_adapter exception: {e}")
        return []


async def _async_get_quote(
    symbol: str,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """
    Fetch real-time quote from FMP.
    
    Args:
        symbol: Trading symbol (e.g., "AAPL")
        timeout: Request timeout
        
    Returns:
        Dict with keys: price, change, changePercent, volume
    """
    api_key = (os.getenv("FMP_API_KEY") or "").strip()
    if not api_key:
        return {}

    symbol = (symbol or "").upper().strip()
    
    request_timeout = min(5.0, max(1.0, float(timeout)))
    
    try:
        url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}?apikey={api_key}"
        
        client = httpx_client.get_client("fmp")
        
        if client is not None:
            resp = await client.get(url, timeout=request_timeout)
        else:
            async with httpx.AsyncClient(timeout=request_timeout) as client_fallback:
                resp = await client_fallback.get(url)
        
        if resp.status_code != 200:
            return {}
        
        data = resp.json()
        
        if not data or not isinstance(data, list) or len(data) == 0:
            return {}
        
        quote = data[0]
        
        return {
            "price": float(quote.get("price", 0)),
            "change": float(quote.get("change", 0)),
            "changePercent": float(quote.get("changesPercentage", 0)),
            "volume": float(quote.get("volume", 0)),
            "dayHigh": float(quote.get("dayHigh", 0)),
            "dayLow": float(quote.get("dayLow", 0)),
            "yearHigh": float(quote.get("yearHigh", 0)),
            "yearLow": float(quote.get("yearLow", 0)),
        }
        
    except Exception as e:
        logger.debug(f"fmp_adapter quote error: {e}")
        return {}


def get_candles(
    symbol: str,
    timeframe: str,
    limit: int = 200,
    timeout: float = 10.0,
) -> List[Dict[str, Any]]:
    """
    Sync-compatible wrapper that runs the async FMP client safely.
    """
    return run_sync(
        _async_get_candles(symbol, timeframe, limit=limit, timeout=timeout)
    )
