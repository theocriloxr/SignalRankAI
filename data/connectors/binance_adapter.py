from __future__ import annotations

from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

try:
    import httpx
except Exception:  # pragma: no cover - optional dependency
    httpx = None

try:
    import requests
except Exception:
    requests = None

from utils.async_runner import run_sync
from utils import httpx_client
from utils import proxy_manager


async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Async implementation using httpx.AsyncClient.

    Returns list of {timestamp, open, high, low, close, volume} or empty list.
    """
    if httpx is None:
        return []

    tf_map = {"5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}
    interval = tf_map.get((timeframe or "").strip(), "1h")
    sym = (symbol or "").upper().strip().replace("/", "").replace("-", "")
    if sym.endswith("USD") and not sym.endswith("USDT"):
        sym = sym[:-3] + "USDT"
    if not sym or len(sym) < 6:
        return []

    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": sym, "interval": interval, "limit": limit}

    try:
        client = httpx_client.get_client("binance")
        if client is not None:
            resp = await client.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                logger.debug("binance_adapter HTTP %s %s", resp.status_code, getattr(resp, "text", "")[:200])
                return []
            payload = resp.json()
        elif requests is not None:
            px = proxy_manager.ccxt_proxy_config_sync().get("proxies") or None
            resp = await __import__("asyncio").to_thread(
                requests.get,
                url,
                params=params,
                timeout=10,
                proxies=px,
            )
            if not getattr(resp, "ok", False):
                return []
            payload = resp.json()
        else:
            async with httpx.AsyncClient(timeout=10.0) as client_fallback:
                resp = await client_fallback.get(url, params=params)
                if resp.status_code != 200:
                    logger.debug("binance_adapter HTTP %s %s", resp.status_code, getattr(resp, "text", "")[:200])
                    return []
                payload = resp.json()

        if not isinstance(payload, list):
            return []

        out: List[Dict[str, Any]] = []
        for row in payload:
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
        return out
    except Exception:
        return []


def get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Sync-compatible wrapper that runs the async client safely.

    Uses `run_sync` shim to avoid `asyncio.run` in running loops.
    """
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit))
