from __future__ import annotations

from typing import List, Dict, Any
import os
import logging

try:
    import httpx
except Exception:
    httpx = None

from utils.async_runner import run_sync
from utils.httpx_client import get_client, retry_async

logger = logging.getLogger(__name__)


async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
    api_key = (os.getenv("POLYGON_API_KEY") or "").strip()
    if not api_key:
        logger.debug("polygon_adapter: POLYGON_API_KEY not set")
        return []
    if httpx is None:
        return []

    # Map timeframe
    tf_map = {"5m": ("5", "minute"), "15m": ("15", "minute"), "1h": ("1", "hour"), "4h": ("4", "hour"), "1d": ("1", "day")}
    multiplier, timespan = tf_map.get(timeframe, ("1", "hour"))

    # Prefix symbol for asset type heuristic
    if ":" not in symbol and symbol.isupper():
        # keep as-is; callers may pass prefixed symbol
        pass

    end_date = __import__('datetime').datetime.utcnow()
    start_date = end_date - __import__('datetime').timedelta(days=200 if timespan == 'day' else 30)
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
    params = {"adjusted": "true", "sort": "asc", "limit": 200, "apiKey": api_key}

    client = get_client()
    if client is None:
        logger.debug("polygon_adapter: httpx client unavailable")
        return []

    async def _do():
        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            if resp.status_code == 429:
                return []
            return []
        data = resp.json()
        results = data.get('results', [])
        if not results:
            return []
        candles = []
        for bar in results:
            try:
                candles.append({
                    'timestamp': int(bar['t']),
                    'open': float(bar['o']),
                    'high': float(bar['h']),
                    'low': float(bar['l']),
                    'close': float(bar['c']),
                    'volume': float(bar.get('v', 0)),
                })
            except Exception:
                continue
        return candles

    try:
        return await retry_async(_do, retries=2, backoff=1.0)
    except Exception as e:
        logger.debug("polygon_adapter error: %s", e)
        return []


def get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit))
