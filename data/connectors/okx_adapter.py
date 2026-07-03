from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from utils.async_runner import run_sync
from utils import httpx_client

logger = logging.getLogger(__name__)


def _normalize_symbol(symbol: str) -> str:
    s = (symbol or "").upper().strip().replace("_", "-").replace("/", "-")
    if "-" in s:
        parts = [p for p in s.split("-") if p]
        if len(parts) >= 2:
            base, quote = parts[0], parts[1]
        else:
            base, quote = s.replace("-", ""), "USDT"
    elif s.endswith("USDT"):
        base, quote = s[:-4], "USDT"
    elif s.endswith("USDC"):
        base, quote = s[:-4], "USDC"
    elif s.endswith("USD"):
        base, quote = s[:-3], "USD"
    else:
        base, quote = s, "USDT"
    return f"{base}-{quote}"


def _map_timeframe(timeframe: str) -> str:
    return {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "1H",
        "4h": "4H",
        "1d": "1D",
    }.get((timeframe or "").strip().lower(), "1H")


async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: int = 10) -> List[Dict[str, Any]]:
    client = httpx_client.get_client("okx")
    if client is None:
        return []

    request_timeout = min(2.5, max(0.1, float(timeout)))
    params = {
        "instId": _normalize_symbol(symbol),
        "bar": _map_timeframe(timeframe),
        "limit": min(int(limit or 200), 300),
    }

    async def _do():
        resp = await client.get(
            "https://www.okx.com/api/v5/market/candles",
            params=params,
            timeout=request_timeout,
        )
        if resp.status_code != 200:
            logger.debug("okx_adapter HTTP %s %s", resp.status_code, getattr(resp, "text", "")[:200])
            return []
        payload = resp.json() or {}
        if str(payload.get("code") or "0") != "0":
            logger.debug("okx_adapter API code=%s msg=%s", payload.get("code"), payload.get("msg"))
            return []
        rows = payload.get("data") or []
        if not isinstance(rows, list):
            return []
        out: List[Dict[str, Any]] = []
        for row in rows:
            try:
                # [ts, open, high, low, close, volume, ...]
                out.append(
                    {
                        "timestamp": int(row[0]),
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
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
        logger.debug("okx_adapter error: %s", exc)
        return []


def get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: int = 10) -> List[Dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit, timeout=timeout))
