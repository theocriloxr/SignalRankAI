from __future__ import annotations

from typing import List, Dict, Any
import os
import logging
import asyncio
from datetime import datetime, timezone
from data.symbol_formatter import format_symbol_for_twelvedata

try:
    import httpx
except Exception:
    httpx = None

from utils.async_runner import run_sync
from utils import httpx_client

logger = logging.getLogger(__name__)


async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
    if httpx is None:
        return []
    # TwelveData requires API key; read from env
    api_key = (os.getenv("TWELVEDATA_API_KEY") or os.getenv("TWELVE_DATA_API_KEY") or "").strip()
    if not api_key:
        logger.debug("twelvedata_adapter: TWELVEDATA_API_KEY not set")
        return []
    from data.providers import _is_cooldown_active, _maybe_apply_rate_limit_cooldown
    if _is_cooldown_active("twelvedata"):
        return []
    url = "https://api.twelvedata.com/time_series"
    tf_map = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h", "1d": "1day"}
    interval = tf_map.get(timeframe)
    if interval is None:
        return []
    requested = max(2, min(5000, int(limit or 200)))
    params = {"symbol": format_symbol_for_twelvedata(symbol), "interval": interval,
              "outputsize": requested, "timezone": "UTC", "apikey": api_key}
    client = httpx_client.get_client("twelvedata")
    if client is None:
        logger.debug("twelvedata_adapter: httpx client unavailable")
        return []
    request_timeout = 2.5

    async def _do():
        resp = await client.get(url, params=params, timeout=request_timeout)
        if resp.status_code == 429:
            _maybe_apply_rate_limit_cooldown("twelvedata", status_code=429)
            logger.warning("[twelvedata] quota_limited; provider cooldown applied")
            return []
        if resp.status_code != 200:
            return []
        data = resp.json()
        if data.get("status") == "error":
            limited = _maybe_apply_rate_limit_cooldown(
                "twelvedata", message=str(data.get("message") or ""))
            logger.warning("[twelvedata] rejected symbol=%s reason=%s", symbol,
                           "quota_limited" if limited else "provider_rejected")
            return []
        values = data.get("values", [])
        if not values:
            return []
        candles = []
        for bar in values:
            try:
                dt = datetime.fromisoformat(bar["datetime"].replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                candles.append(
                    {
                        "timestamp": int(dt.timestamp() * 1000),
                        "open": float(bar.get("open", 0)),
                        "high": float(bar.get("high", 0)),
                        "low": float(bar.get("low", 0)),
                        "close": float(bar.get("close", 0)),
                        "volume": float(bar.get("volume", 0)),
                    }
                )
            except Exception:
                continue
        candles.sort(key=lambda item: int(item.get("timestamp") or 0))
        return candles[-requested:]

    try:
        return await asyncio.wait_for(
            httpx_client.retry_async(_do, retries=2, backoff=0.5),
            timeout=request_timeout,
        )
    except Exception as e:
        logger.debug("twelvedata_adapter error_type=%s", type(e).__name__)
        return []


def get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit))
