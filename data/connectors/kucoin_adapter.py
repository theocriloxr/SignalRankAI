"""
KuCoin Adapter - Free Crypto Fallback Provider

No API key required! Public endpoints are open.
Format: BTC-USDT (replace "/" with "-")
Timeframe mapping: 1h -> 1hour, 4h -> 4hour, 1d -> 1day

Docs: https://docs.kucoin.com/#/en/market/candles
"""
from __future__ import annotations

from typing import List, Dict, Any
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
    timeout: float = 5.0,
) -> List[Dict[str, Any]]:
    """
    Fetch candles from KuCoin public API.
    
    Args:
        symbol: Trading symbol (e.g., "BTC/USDT", "ETHUSDT")
        timeframe: Timeframe (1h, 4h, 1d)
        limit: Number of candles to fetch
        timeout: Request timeout
        
    Returns:
        List of candle dicts with keys: timestamp, open, high, low, close, volume
    """
    if httpx is None:
        logger.debug("kucoin_adapter: httpx not available")
        return []

    # 1. Translate Binance format (BTC/USDT) to KuCoin format (BTC-USDT)
    symbol = (symbol or "").upper().strip()
    # Remove common separators
    symbol = symbol.replace("/", "-").replace("_", "").replace("-", "")
    
    # Handle USDT suffix - KuCoin uses USDT for crypto
    if symbol.endswith("USDT") or symbol.endswith("USD"):
        # Keep as-is for KuCoin
        pass
    
    # 2. Map timeframe strings (KuCoin uses '1hour' instead of '1h')
    tf_map = {
        "1m": "1min",
        "5m": "5min", 
        "15m": "15min",
        "1h": "1hour",
        "4h": "4hour",
        "1d": "1day"
    }
    kc_tf = tf_map.get((timeframe or "").strip().lower(), "1hour")
    
    # Build URL
    url = f"https://api.kucoin.com/api/v1/market/candles?type={kc_tf}&symbol={symbol}"
    
    request_timeout = min(5.0, max(1.0, float(timeout)))
    
    try:
        client = httpx_client.get_client("kucoin")
        
        if client is not None:
            resp = await client.get(url, timeout=request_timeout)
        else:
            async with httpx.AsyncClient(timeout=request_timeout) as client_fallback:
                resp = await client_fallback.get(url)
        
        if resp.status_code != 200:
            logger.debug(f"kucoin_adapter HTTP {resp.status_code}: {getattr(resp, 'text', '')[:200]}")
            return []
        
        data = resp.json()
        
        # KuCoin returns: {"code": "200000", "data": [[timestamp, open, close, high, low, volume], ...]}
        code = data.get("code")
        if code != "200000":
            logger.debug(f"kucoin_adapter error code: {code}")
            return []
        
        candles_data = data.get("data")
        if not candles_data or not isinstance(candles_data, list):
            return []
        
        out: List[Dict[str, Any]] = []
        
        # KuCoin returns most recent first, so reverse to get chronological order
        for row in candles_data[:limit]:
            try:
                # Row format: [timestamp, open, close, high, low, volume]
                # timestamp is in seconds
                ts = int(row[0])
                
                out.append({
                    "timestamp": ts,
                    "open": float(row[1]),
                    "close": float(row[2]),
                    "high": float(row[3]),
                    "low": float(row[4]),
                    "volume": float(row[5]) if len(row) > 5 else 0.0,
                })
            except (IndexError, ValueError) as e:
                logger.debug(f"kucoin_adapter parse error: {e}")
                continue
        
        # Reverse to chronological (oldest to newest)
        return out[::-1]
        
    except Exception as e:
        logger.debug(f"kucoin_adapter exception: {e}")
        return []


def get_candles(
    symbol: str,
    timeframe: str,
    limit: int = 200,
    timeout: float = 5.0,
) -> List[Dict[str, Any]]:
    """
    Sync-compatible wrapper that runs the async KuCoin client safely.
    
    Uses `run_sync` shim to avoid `asyncio.run` in running loops.
    """
    return run_sync(
        _async_get_candles(symbol, timeframe, limit=limit, timeout=timeout)
    )
