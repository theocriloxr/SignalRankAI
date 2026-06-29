"""
FCS Adapter - Financial Content Services API

API Key required: FCS_API_KEY (or FCS_API_SECRET)
Free Tier: Varies (check https://fcsapi.com/)
Best for: Crypto, Forex, Stocks

Docs: https://fcsapi.com/docs
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
    Fetch candles from FCS API.
    
    Args:
        symbol: Trading symbol (e.g., "BTC/USDT", "EURUSD")
        timeframe: Timeframe (1h, 4h, 1d) 
        limit: Number of candles to fetch
        timeout: Request timeout
        
    Returns:
        List of candle dicts with keys: timestamp, open, high, low, close, volume
    """
    api_key = (os.getenv("FCS_API_KEY") or os.getenv("FCS_API_SECRET") or "").strip()
    if not api_key:
        logger.debug("fcs_adapter: FCS_API_KEY not set")
        return []

    # Clean symbol - FCS uses format like BTCUSDT, EURUSD
    symbol = (symbol or "").upper().strip()
    symbol_clean = symbol.replace("/", "").replace("-", "").replace("_", "")
    
    request_timeout = min(10.0, max(2.0, float(timeout)))
    
    # FCS uses different timeframe format
    # 1h, 2h, 4h, 6h, 12h, 1d, 1w
    tf_map = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "6h": "6h",
        "12h": "12h",
        "1d": "1d",
        "1w": "1w"
    }
    fcs_tf = tf_map.get((timeframe or "").strip().lower(), "1h")
    
    # API ID for FCS - checking different possible IDs based on their docs
    # The format is typically: https://fcsapi.com/api/v3/{indicator}/...
    try:
        # Try standard candles endpoint
        url = (
            f"https://fcsapi.com/api/v3/candles?"
            f"symbol={symbol_clean}&"
            f"timeframe={fcs_tf}&"
            f"accessKey={api_key}"
        )
        
        client = httpx_client.get_client("fcs")
        
        if client is not None:
            resp = await client.get(url, timeout=request_timeout)
        else:
            async with httpx.AsyncClient(timeout=request_timeout) as client_fallback:
                resp = await client_fallback.get(url)
        
        if resp.status_code != 200:
            logger.debug(f"fcs_adapter HTTP {resp.status_code}: {getattr(resp, 'text', '')[:200]}")
            return []
        
        data = resp.json()
        
        # FCS response format: {"candles": [...], "status": "ok"}
        if not data or not isinstance(data, dict):
            return []
        
        # Check for API error
        status = data.get("status")
        if status == "error" or data.get("err"):
            err_msg = data.get("message", data.get("err", "unknown"))
            logger.debug(f"fcs_adapter API error: {err_msg}")
            return []
        
        candles_data = data.get("candles") or data.get("data") or []
        if not candles_data:
            return []
        
        out: List[Dict[str, Any]] = []
        
        # FCS format: [[timestamp, open, high, low, close, volume], ...]
        for row in candles_data[:limit]:
            try:
                if isinstance(row, list) and len(row) >= 6:
                    out.append({
                        "timestamp": int(row[0]),
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume": float(row[5]),
                    })
                elif isinstance(row, dict):
                    out.append({
                        "timestamp": int(row.get("t", row.get("timestamp", 0))),
                        "open": float(row.get("o", row.get("open", 0))),
                        "high": float(row.get("h", row.get("high", 0))),
                        "low": float(row.get("l", row.get("low", 0))),
                        "close": float(row.get("c", row.get("close", 0))),
                        "volume": float(row.get("v", row.get("volume", 0))),
                    })
            except (ValueError, TypeError) as e:
                logger.debug(f"fcs_adapter parse error: {e}")
                continue
        
        # FCS typically returns newest first, reverse to chronological
        return out[::-1]
        
    except Exception as e:
        logger.debug(f"fcs_adapter exception: {e}")
        return []


async def _async_get_latest_price(
    symbol: str,
    timeout: float = 5.0,
) -> float:
    """
    Fetch latest price from FCS API.
    
    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
        timeout: Request timeout
        
    Returns:
        Latest price or 0.0 on failure
    """
    api_key = (os.getenv("FCS_API_KEY") or os.getenv("FCS_API_SECRET") or "").strip()
    if not api_key:
        return 0.0

    symbol = (symbol or "").upper().strip().replace("/", "").replace("-", "").replace("_", "")
    
    request_timeout = min(5.0, max(1.0, float(timeout)))
    
    try:
        url = f"https://fcsapi.com/api/v1/latest_price?symbol={symbol}&accessKey={api_key}"
        
        client = httpx_client.get_client("fcs")
        
        if client is not None:
            resp = await client.get(url, timeout=request_timeout)
        else:
            async with httpx.AsyncClient(timeout=request_timeout) as client_fallback:
                resp = await client_fallback.get(url)
        
        if resp.status_code != 200:
            return 0.0
        
        data = resp.json()
        
        # FCS returns: {"price": {"symbol": "BTCUSDT", "price": 12345.67}}
        price_data = data.get("price", {})
        if isinstance(price_data, dict):
            return float(price_data.get("price", 0))
        
        return 0.0
        
    except Exception as e:
        logger.debug(f"fcs_adapter price error: {e}")
        return 0.0


def get_candles(
    symbol: str,
    timeframe: str,
    limit: int = 200,
    timeout: float = 10.0,
) -> List[Dict[str, Any]]:
    """
    Sync-compatible wrapper that runs the async FCS client safely.
    """
    return run_sync(
        _async_get_candles(symbol, timeframe, limit=limit, timeout=timeout)
    )
