from __future__ import annotations

from typing import List, Dict, Any
import logging

from utils.async_runner import run_sync
from utils import httpx_client

logger = logging.getLogger(__name__)


def _normalize_symbol(symbol: str) -> str:
    s = (symbol or "").upper().strip().replace("/", "").replace("-", "")
    if s.endswith("USD") and not s.endswith("USDT"):
        s = s[:-3] + "USDT"
    return s


def _map_timeframe(timeframe: str) -> str:
    return {
        "5m": "5",
        "15m": "15",
        "1h": "60",
        "4h": "240",
        "1d": "D",
    }.get((timeframe or "").strip(), "60")


async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: int = 10) -> List[Dict[str, Any]]:
    client = httpx_client.get_client("bybit")
    if client is None:
        return []

    params = {
        "category": "spot",
        "symbol": _normalize_symbol(symbol),
        "interval": _map_timeframe(timeframe),
        "limit": int(limit),
    }

    async def _do():
        resp = await client.get("https://api.bybit.com/v5/market/klines", params=params, timeout=timeout)
        if resp.status_code != 200:
            return []
        payload = resp.json() or {}
        if str(payload.get("retCode") or "0") != "0":
            return []
        rows = ((payload.get("result") or {}).get("list") or [])
        if not isinstance(rows, list):
            return []
        out: List[Dict[str, Any]] = []
        for row in rows:
            try:
                out.append(
                    {
                        "timestamp": int(row[0]),
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume": float(row[5]),
                    }
                )
            except Exception:
                continue
        # Bybit returns newest-first for this endpoint; normalize to ascending time.
        out.sort(key=lambda c: int(c.get("timestamp") or 0))
        return out

    try:
        return await httpx_client.retry_async(_do, retries=2, backoff=0.5)
    except Exception as exc:
        logger.debug("bybit_adapter error: %s", exc)
        return []


def get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: int = 10) -> List[Dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit, timeout=timeout))
