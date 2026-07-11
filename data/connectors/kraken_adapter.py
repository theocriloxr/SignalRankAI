from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from utils.async_runner import run_sync
from utils import httpx_client

logger = logging.getLogger(__name__)


def _normalize_pair(symbol: str) -> str:
    s = (symbol or "").upper().strip().replace("_", "").replace("/", "").replace("-", "")
    if s.endswith("USDT"):
        base, quote = s[:-4], "USD"
    elif s.endswith("USDC"):
        base, quote = s[:-4], "USD"
    elif s.endswith("USD"):
        base, quote = s[:-3], "USD"
    else:
        base, quote = s, "USD"
    # Kraken accepts common unprefixed WS/API aliases like BTCUSD and ETHUSD.
    return f"{base}{quote}"


def _interval_minutes(timeframe: str) -> int:
    return {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "1h": 60,
        "4h": 240,
        "1d": 1440,
    }.get((timeframe or "").strip().lower(), 60)


async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: int = 10) -> List[Dict[str, Any]]:
    client = httpx_client.get_client("kraken")
    if client is None:
        return []

    request_timeout = min(2.5, max(0.1, float(timeout)))
    params = {"pair": _normalize_pair(symbol), "interval": _interval_minutes(timeframe)}

    async def _do():
        resp = await client.get("https://api.kraken.com/0/public/OHLC", params=params, timeout=request_timeout)
        if resp.status_code != 200:
            logger.debug("kraken_adapter HTTP %s %s", resp.status_code, getattr(resp, "text", "")[:200])
            return []
        payload = resp.json() or {}
        if payload.get("error"):
            logger.debug("kraken_adapter API error=%s", payload.get("error"))
            return []
        result = payload.get("result") or {}
        rows = []
        for key, value in result.items():
            if key != "last" and isinstance(value, list):
                rows = value
                break
        out: List[Dict[str, Any]] = []
        for row in rows[-int(limit or 200):]:
            try:
                # [time_seconds, open, high, low, close, vwap, volume, count]
                out.append(
                    {
                        "timestamp": int(row[0]) * 1000,
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume": float(row[6] or 0.0),
                    }
                )
            except Exception:
                continue
        out.sort(key=lambda c: int(c.get("timestamp") or 0))
        return out

    try:
        return await asyncio.wait_for(httpx_client.retry_async(_do, retries=2, backoff=0.5), timeout=request_timeout)
    except Exception as exc:
        logger.debug("kraken_adapter error: %s", exc)
        return []


def get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: int = 10) -> List[Dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit, timeout=timeout))
