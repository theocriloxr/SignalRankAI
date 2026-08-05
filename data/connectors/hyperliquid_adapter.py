"""Hyperliquid public market-data adapter (venue = hyperliquid, not an asset class).

Supports mainnet and testnet REST ``/info`` endpoints:

- instrument discovery (``meta``)
- candle snapshots (``candlesSnapshot``)
- L2 order book (``l2Book``)
- mark / oracle / funding / open interest (``metaAndAssetCtxs``)

Fail-closed by default: ``HYPERLIQUID_MARKET_DATA_ENABLED`` must be explicitly
``1``/``true`` before any network call is made (Phase 16/24 feature-gate rule).
This adapter is market data ONLY — execution lives in a separate testnet
adapter behind ``HYPERLIQUID_TESTNET_ENABLED`` and never activates live orders.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

from utils.async_runner import run_sync
from utils import httpx_client

logger = logging.getLogger(__name__)

MAINNET_API_URL = "https://api.hyperliquid.xyz"
TESTNET_API_URL = "https://api.hyperliquid-testnet.xyz"

#: Hyperliquid candle intervals: 1m 3m 5m 15m 30m 1h 2h 4h 1d
_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "1d": "1d",
}

#: Coins that have no perpetual/spot market on Hyperliquid are skipped without
#: retrying (permanent unsupported-symbol cache to prevent retry storms).
_UNSUPPORTED_CACHE: dict[str, float] = {}
_UNSUPPORTED_CACHE_TTL_SECONDS = 12 * 60 * 60
_META_CTX_CACHE: dict[str, tuple[float, Dict[str, Dict[str, Any]]]] = {}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "y"}


def _market_data_enabled() -> bool:
    return _env_bool("HYPERLIQUID_MARKET_DATA_ENABLED", False)


def _testnet_enabled() -> bool:
    return _env_bool("HYPERLIQUID_TESTNET", False)


def api_url() -> str:
    return TESTNET_API_URL if _testnet_enabled() else MAINNET_API_URL


def _normalize_coin(symbol: str) -> str:
    """Map canonical symbols (BTCUSDT, BTC/USDT, BTC) to Hyperliquid coin names."""
    s = (symbol or "").upper().strip().replace("/", "").replace("_", "").replace("-", "")
    for suffix in ("USDT", "USDC", "USD", "PERP"):
        if s.endswith(suffix) and len(s) > len(suffix):
            s = s[: -len(suffix)]
            break
    return s


def _map_interval(timeframe: str) -> Optional[str]:
    return _INTERVAL_MAP.get((timeframe or "").strip().lower())


async def _post_info(payload: Dict[str, Any], timeout: float = 5.0) -> Optional[Any]:
    client = httpx_client.get_client("hyperliquid")
    if client is None:
        return None

    async def _do():
        resp = await client.post(f"{api_url()}/info", json=payload, timeout=timeout)
        if resp.status_code != 200:
            logger.debug("hyperliquid HTTP %s payload_type=%s", resp.status_code, payload.get("type"))
            return None
        return resp.json()

    try:
        return await asyncio.wait_for(httpx_client.retry_async(_do, retries=2, backoff=0.5), timeout=timeout + 1.0)
    except Exception as exc:
        logger.debug("hyperliquid info error type=%s: %s", payload.get("type"), exc)
        return None


async def _async_get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: int = 8) -> List[Dict[str, Any]]:
    if not _market_data_enabled():
        return []
    interval = _map_interval(timeframe)
    if interval is None:
        return []
    coin = _normalize_coin(symbol)
    if not coin:
        return []
    now_ms = int(time.time() * 1000)
    if coin in _UNSUPPORTED_CACHE and _UNSUPPORTED_CACHE[coin] > time.monotonic():
        return []
    # Request roughly limit+1 candles worth of history from now.
    seconds_per_interval = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "2h": 7200, "4h": 14400, "1d": 86400}
    span_ms = seconds_per_interval.get(interval, 3600) * max(1, int(limit or 200) + 1) * 1000
    payload = {
        "type": "candlesSnapshot",
        "req": {
            "coin": coin,
            "interval": interval,
            "startTime": now_ms - span_ms,
            "endTime": now_ms,
        },
    }
    rows = await _post_info(payload, timeout=float(timeout))
    if not isinstance(rows, list) or not rows:
        if rows == []:
            _UNSUPPORTED_CACHE[coin] = time.monotonic() + _UNSUPPORTED_CACHE_TTL_SECONDS
        return []
    out: List[Dict[str, Any]] = []
    for row in rows[-int(limit or 200):]:
        try:
            out.append(
                {
                    "timestamp": int(row["t"]),
                    "open": float(row["o"]),
                    "high": float(row["h"]),
                    "low": float(row["l"]),
                    "close": float(row["c"]),
                    "volume": float(row["v"] or 0.0),
                }
            )
        except Exception:
            continue
    return out


def get_candles(symbol: str, timeframe: str, limit: int = 200, timeout: int = 10) -> List[Dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit, timeout=timeout))


async def _async_get_meta_ctx() -> Dict[str, Dict[str, Any]]:
    """Return {COIN: {mark_px, funding, open_interest, prev_day_px, oracle_px}}."""
    cached = _META_CTX_CACHE.get("ctx")
    if cached and cached[0] > time.monotonic():
        return cached[1]
    rows = await _post_info({"type": "metaAndAssetCtxs"}, timeout=5.0)
    if not isinstance(rows, list):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        try:
            coin = str((row.get("coin") or "")).upper().strip()
            if not coin:
                continue
            out[coin] = {
                "mark_px": _safe_float(row.get("markPx")),
                "oracle_px": _safe_float(row.get("oraclePx")),
                "funding": _safe_float(row.get("funding")),
                "open_interest": _safe_float(row.get("openInterest")),
                "prev_day_px": _safe_float(row.get("prevDayPx")),
                "day_ntl_vlm": _safe_float(row.get("dayNtlVlm")),
            }
        except Exception:
            continue
    if out:
        _META_CTX_CACHE["ctx"] = (time.monotonic() + 15.0, out)
    return out


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if parsed == parsed else default
    except Exception:
        return default


async def _async_get_funding(symbol: str) -> Optional[float]:
    """Current funding rate for a perpetual (8h rate as provided by the venue)."""
    if not _market_data_enabled():
        return None
    ctx = await _async_get_meta_ctx()
    row = ctx.get(_normalize_coin(symbol))
    if row is None or not row.get("funding"):
        return None
    return row["funding"]


def get_funding(symbol: str) -> Optional[float]:
    return run_sync(_async_get_funding(symbol))


async def _async_get_mark_price(symbol: str) -> Optional[float]:
    if not _market_data_enabled():
        return None
    ctx = await _async_get_meta_ctx()
    row = ctx.get(_normalize_coin(symbol))
    if row is None or not row.get("mark_px"):
        return None
    return row["mark_px"]


def get_mark_price(symbol: str) -> Optional[float]:
    return run_sync(_async_get_mark_price(symbol))


async def _async_get_order_book(symbol: str, depth: int = 20) -> Optional[Dict[str, Any]]:
    if not _market_data_enabled():
        return None
    payload = {"type": "l2Book", "coin": _normalize_coin(symbol)}
    data = await _post_info(payload, timeout=5.0)
    if not isinstance(data, dict):
        return None
    levels = data.get("levels") or []
    bids_raw = levels[0] if len(levels) > 0 else []
    asks_raw = levels[1] if len(levels) > 1 else []
    bids: list[tuple[float, float]] = []
    asks: list[tuple[float, float]] = []
    for level in bids_raw[: max(1, int(depth))]:
        try:
            bids.append((float(level[0]), float(level[1])))
        except Exception:
            continue
    for level in asks_raw[: max(1, int(depth))]:
        try:
            asks.append((float(level[0]), float(level[1])))
        except Exception:
            continue
    return {"bids": bids, "asks": asks, "time": int(data.get("time", 0) or 0)}


def get_order_book(symbol: str, depth: int = 20) -> Optional[Dict[str, Any]]:
    return run_sync(_async_get_order_book(symbol, depth=depth))


def health() -> Dict[str, Any]:
    """Zero-network provider health probe (env gate + endpoint config only)."""
    enabled = _market_data_enabled()
    return {
        "provider_id": "hyperliquid",
        "enabled": enabled,
        "network": "testnet" if _testnet_enabled() else "mainnet",
        "api_url": api_url(),
        "state": "disabled" if not enabled else "configured",
    }


__all__ = [
    "api_url",
    "get_candles",
    "get_funding",
    "get_mark_price",
    "get_order_book",
    "health",
]
