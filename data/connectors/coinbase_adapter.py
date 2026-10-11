from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from utils.async_runner import run_sync
from utils import httpx_client
from data.connectors.sdk_adapters import crypto_pair

logger = logging.getLogger(__name__)


def _normalize_product(symbol: str) -> str:
    pair = crypto_pair(symbol)
    return pair.replace("/", "-") if pair else ""


def _granularity_seconds(timeframe: str) -> int:
    return {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "1h": 3600,
        "1d": 86400,
    }.get((timeframe or "").strip().lower(), 0)


async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: int = 10) -> List[Dict[str, Any]]:
    client = httpx_client.get_client("coinbase")
    if client is None:
        return []

    request_timeout = min(2.5, max(0.1, float(timeout)))
    product = _normalize_product(symbol)
    params = {"granularity": _granularity_seconds(timeframe)}
    if not product or not params["granularity"]:
        return []

    async def _do():
        resp = await client.get(
            f"https://api.exchange.coinbase.com/products/{product}/candles",
            params=params,
            timeout=request_timeout,
        )
        if resp.status_code != 200:
            logger.debug("coinbase_adapter HTTP %s %s", resp.status_code, getattr(resp, "text", "")[:200])
            return []
        rows = resp.json() or []
        if not isinstance(rows, list):
            return []
        out: List[Dict[str, Any]] = []
        for row in rows[: int(limit or 200)]:
            try:
                # [time_seconds, low, high, open, close, volume]
                out.append(
                    {
                        "timestamp": int(row[0]) * 1000,
                        "open": float(row[3]),
                        "high": float(row[2]),
                        "low": float(row[1]),
                        "close": float(row[4]),
                        "volume": float(row[5] or 0.0),
                    }
                )
            except Exception:
                continue
        out.sort(key=lambda c: int(c.get("timestamp") or 0))
        return out

    try:
        return await asyncio.wait_for(httpx_client.retry_async(_do, retries=2, backoff=0.5), timeout=request_timeout)
    except Exception as exc:
        logger.debug("coinbase_adapter error: %s", exc)
        return []


def get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: int = 10) -> List[Dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit, timeout=timeout))
