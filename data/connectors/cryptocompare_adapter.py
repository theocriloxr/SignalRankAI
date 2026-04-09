"""Async CryptoCompare connector adapter using httpx AsyncClient."""
from __future__ import annotations

import os
import asyncio
import logging
from typing import List

from utils.httpx_client import get_client, retry_async

logger = logging.getLogger(__name__)


def _map_tf(tf: str):
    tf = (tf or "").strip()
    if tf in {"5m", "15m"}:
        return "histominute", 5 if tf == "5m" else 15
    if tf in {"1h", "4h"}:
        return "histohour", 1 if tf == "1h" else 4
    return "histoday", 1


async def _fetch_for_quote(client, base_raw: str, tsym: str, endpoint: str, aggregate: int, timeout: int):
    url = f"https://min-api.cryptocompare.com/data/v2/{endpoint}"
    params = {
        "fsym": base_raw,
        "tsym": tsym,
        "limit": 200,
        "aggregate": aggregate,
    }
    api_key = (os.getenv("CRYPTOCOMPARE_API_KEY") or "").strip()
    headers = {"authorization": f"Apikey {api_key}"} if api_key else {}

    async def call():
        if client is None:
            raise RuntimeError("no httpx client")
        resp = await client.get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    data = None
    try:
        data = await retry_async(call, retries=2, backoff=1.0)
    except Exception as e:
        logger.debug("[cryptocompare] request failed %s %s", base_raw, e)
        return []

    payload = data or {}
    if str(payload.get("Response") or "").lower() != "success":
        return []
    items = (((payload.get("Data") or {}) or {}).get("Data") or [])
    if not isinstance(items, list) or not items:
        return []

    out = []
    for row in items:
        try:
            ts_ms = int(row.get("time")) * 1000
            out.append({
                "timestamp": ts_ms,
                "open": float(row.get("open")),
                "high": float(row.get("high")),
                "low": float(row.get("low")),
                "close": float(row.get("close")),
                "volume": float(row.get("volumefrom") or 0.0),
            })
        except Exception:
            continue
    return out


async def cryptocompare_get_candles(symbol: str, timeframe: str, timeout: int = 10) -> List[dict]:
    base_raw = (symbol or "").upper().strip()
    if not base_raw:
        return []

    # choose preferred quote
    preferred_quote = "USDT"
    for q in ("USDT", "USDC", "BUSD", "USD"):
        if base_raw.endswith(q) and len(base_raw) > len(q):
            base_raw = base_raw[: -len(q)]
            preferred_quote = q
            break

    endpoint, aggregate = _map_tf(timeframe)

    client = get_client("cryptocompare")
    # Try preferred quote, then fallbacks
    for tsym in (preferred_quote, "USDT", "USD", "USDC", "BUSD"):
        try:
            if client is None:
                # no httpx client available; run blocking fallback
                import requests

                url = f"https://min-api.cryptocompare.com/data/v2/{endpoint}"
                params = {"fsym": base_raw, "tsym": tsym, "limit": 200, "aggregate": aggregate}
                api_key = (os.getenv("CRYPTOCOMPARE_API_KEY") or "").strip()
                headers = {"authorization": f"Apikey {api_key}"} if api_key else {}
                resp = requests.get(url, params=params, headers=headers, timeout=timeout)
                if not resp.ok:
                    continue
                payload = resp.json() or {}
                if str(payload.get("Response") or "").lower() != "success":
                    continue
                data = (((payload.get("Data") or {}) or {}).get("Data") or [])
                if data:
                    return await asyncio.to_thread(lambda: [
                        {
                            "timestamp": int(row.get("time")) * 1000,
                            "open": float(row.get("open")),
                            "high": float(row.get("high")),
                            "low": float(row.get("low")),
                            "close": float(row.get("close")),
                            "volume": float(row.get("volumefrom") or 0.0),
                        }
                        for row in data
                        if row
                    ])
                continue
            else:
                out = await _fetch_for_quote(client, base_raw, tsym, endpoint, aggregate, timeout)
                if out:
                    return out
        except Exception:
            continue
    return []


def cryptocompare_get_candles_sync(symbol: str, timeframe: str, timeout: int = 10):
    """Sync wrapper for environments that expect blocking callables."""
    from utils.async_runner import run_sync

    return run_sync(cryptocompare_get_candles(symbol, timeframe, timeout=timeout))
