from __future__ import annotations

from typing import List, Dict, Any
import logging
import asyncio
import time

logger = logging.getLogger(__name__)

#: Binance answers 451 (and sometimes 403 "restricted location") to requests
#: from restricted jurisdictions/datacenters. That is a deployment-region fact,
#: not a transient error: report it loudly once and stop calling for a while,
#: so the router can fall back to another entitled provider without each scan
#: paying for a doomed request per symbol.
_REGION_BLOCK_COOLDOWN_SECONDS = 900.0
_region_blocked_until = 0.0


def _is_region_block(status_code: int, body: str) -> bool:
    if status_code == 451:
        return True
    lowered = (body or "").lower()
    return status_code == 403 and ("restricted location" in lowered or "eligibility" in lowered)


def _note_http_failure(status_code: int, body: str) -> None:
    global _region_blocked_until
    if _is_region_block(status_code, body):
        first = time.monotonic() >= _region_blocked_until
        _region_blocked_until = time.monotonic() + _REGION_BLOCK_COOLDOWN_SECONDS
        if first:
            logger.warning(
                "binance_adapter region_restricted status=%s: this deployment region cannot use "
                "api.binance.com; suppressing Binance candle requests for %.0fs so other providers are used",
                status_code,
                _REGION_BLOCK_COOLDOWN_SECONDS,
            )
        return
    logger.debug("binance_adapter HTTP %s %s", status_code, (body or "")[:200])


def region_restricted() -> bool:
    """True while a recent 451/restricted-location answer is being honoured."""
    return time.monotonic() < _region_blocked_until


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


async def _async_get_candles(
    symbol: str,
    timeframe: str,
    limit: int = 200,
    timeout: float = 2.5,
) -> List[Dict[str, Any]]:
    """Async implementation using httpx.AsyncClient.

    Returns list of {timestamp, open, high, low, close, volume} or empty list.
    """
    if httpx is None or region_restricted():
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

    request_timeout = min(2.5, max(0.1, float(timeout)))
    try:
        client = httpx_client.get_client("binance")
        if client is not None:
            resp = await asyncio.wait_for(
                client.get(url, params=params, timeout=request_timeout),
                timeout=request_timeout,
            )
            if resp.status_code != 200:
                _note_http_failure(resp.status_code, str(getattr(resp, "text", "") or ""))
                return []
            payload = resp.json()
        elif requests is not None:
            px = proxy_manager.ccxt_proxy_config_sync().get("proxies") or None
            resp = await asyncio.wait_for(
                __import__("asyncio").to_thread(
                    requests.get,
                    url,
                    params=params,
                    timeout=request_timeout,
                    proxies=px,
                ),
                timeout=request_timeout,
            )
            if not getattr(resp, "ok", False):
                _note_http_failure(int(getattr(resp, "status_code", 0) or 0), str(getattr(resp, "text", "") or ""))
                return []
            payload = resp.json()
        else:
            async with httpx.AsyncClient(timeout=request_timeout) as client_fallback:
                resp = await asyncio.wait_for(
                    client_fallback.get(url, params=params),
                    timeout=request_timeout,
                )
                if resp.status_code != 200:
                    _note_http_failure(resp.status_code, str(getattr(resp, "text", "") or ""))
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


def get_candles(
    symbol: str,
    timeframe: str,
    limit: int = 200,
    timeout: float = 2.5,
) -> List[Dict[str, Any]]:
    """Sync-compatible wrapper that runs the async client safely.

    Uses `run_sync` shim to avoid `asyncio.run` in running loops.
    """
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit, timeout=timeout))
