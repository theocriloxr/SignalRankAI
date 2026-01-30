from __future__ import annotations

from typing import List, Dict, Any

try:
    import httpx
except Exception:
    httpx = None

from utils.async_runner import run_sync
from utils.httpx_client import get_client, retry_async


async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
    if httpx is None:
        return []
    # TwelveData requires API key; we'll read at runtime in caller
    api_key = "e37143a64e9340c8a585771b3f0ffcc0"  # TODO: Set your TwelveData API key here or pass it as a parameter
    url = "https://api.twelvedata.com/time_series"
    tf_map = {"5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1day"}
    interval = tf_map.get(timeframe, "1h")
    params = {"symbol": symbol, "interval": interval, "outputsize": 200, "apikey": api_key}
    client = get_client()
    if client is None:
        return []

    async def _do():
        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            return []
        data = resp.json()
        if data.get("status") == "error":
            return []
        values = data.get("values", [])
        if not values:
            return []
        candles = []
        from datetime import datetime
        for bar in values:
            try:
                dt = datetime.fromisoformat(bar["datetime"].replace("Z", ""))
                candles.append({
                    "timestamp": int(dt.timestamp() * 1000),
                    "open": float(bar.get("open", 0)),
                    "high": float(bar.get("high", 0)),
                    "low": float(bar.get("low", 0)),
                    "close": float(bar.get("close", 0)),
                    "volume": float(bar.get("volume", 0)),
                })
            except Exception:
                continue
        return candles

    try:
        return await retry_async(_do, retries=2, backoff=0.5)
    except Exception:
        return []


def get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit))
