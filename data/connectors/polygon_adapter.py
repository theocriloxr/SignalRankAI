from __future__ import annotations

from typing import List, Dict, Any
import os
import logging
import asyncio
from datetime import datetime, timedelta

try:
    import httpx
except Exception:
    httpx = None

from utils.async_runner import run_sync
from utils import httpx_client

logger = logging.getLogger(__name__)


def _resolved_api_key() -> str:
    """Massive (formerly Polygon.io) credential consolidation.

    One resolved secret: ``MASSIVE_API_KEY`` wins, ``POLYGON_API_KEY`` is the
    backward-compatible alias.  Never require both variables.
    """
    return (os.getenv("MASSIVE_API_KEY") or "").strip() or (os.getenv("POLYGON_API_KEY") or "").strip()


def _resolved_base_url() -> str:
    return (os.getenv("MASSIVE_API_BASE_URL") or "").strip() or "https://api.polygon.io"


def _enabled() -> bool:
    raw = os.getenv("MASSIVE_MARKET_DATA_ENABLED")
    if raw is None:
        return True  # polygon behaviour unchanged unless explicitly disabled
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
    api_key = _resolved_api_key()
    if not api_key or not _enabled():
        logger.debug("polygon_adapter: massive/polygon disabled or key not set")
        return []
    if httpx is None:
        return []

    # Map timeframe
    tf_map = {
        "1m": ("1", "minute"),
        "3m": ("3", "minute"),
        "5m": ("5", "minute"),
        "15m": ("15", "minute"),
        "30m": ("30", "minute"),
        "1h": ("1", "hour"),
        "4h": ("4", "hour"),
        "1d": ("1", "day"),
    }
    interval = tf_map.get(str(timeframe or "").strip().lower())
    if interval is None:
        return []
    multiplier, timespan = interval
    requested_limit = max(1, min(5000, int(limit)))

    # Prefix symbol for asset type heuristic
    if ":" not in symbol and symbol.isupper():
        # keep as-is; callers may pass prefixed symbol
        pass

    end_date = datetime.now()
    start_date = end_date - timedelta(days=200 if timespan == "day" else 30)
    url = f"{_resolved_base_url()}/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
    # The API limit counts base aggregates, not output candles. Request newest
    # bars first so a bounded response does not select the start of the month.
    base_multiplier = int(multiplier) * (60 if timespan == "hour" else 1)
    params = {"adjusted": "true", "sort": "desc", "limit": min(50000, requested_limit * base_multiplier), "apiKey": api_key}
    request_timeout = 2.5

    async def _do():
        # Resolve client inside _do() so test patches to get_client are respected at call time
        _client = httpx_client.get_client("polygon")
        if _client is None:
            logger.debug("polygon_adapter: httpx client unavailable")
            return []
        resp = await _client.get(url, params=params, timeout=request_timeout)
        if resp.status_code != 200:
            if resp.status_code == 429:
                return []
            return []
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return []
        candles = []
        for bar in results:
            try:
                candles.append(
                    {
                        "timestamp": int(bar["t"]),
                        "open": float(bar["o"]),
                        "high": float(bar["h"]),
                        "low": float(bar["l"]),
                        "close": float(bar["c"]),
                        "volume": float(bar.get("v", 0)),
                    }
                )
            except Exception:
                continue
        return sorted(candles, key=lambda candle: candle["timestamp"])[-requested_limit:]

    try:
        return await asyncio.wait_for(
            httpx_client.retry_async(_do, retries=2, backoff=1.0),
            timeout=request_timeout,
        )
    except Exception as e:
        logger.debug("polygon_adapter error: %s", e)
        return []


def get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit))
