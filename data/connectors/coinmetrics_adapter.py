"""Coin Metrics Community API adapter (keyless public market + network data).

Roles (provider addendum §16):
* free historical market candles and network metrics via the Community API
* optional Pro API upgrade via ``COIN_METRICS_API_KEY``
* never an execution venue

The Community API returns unix-second timestamps in ms (``time`` field).
Candle series use ``timeseries/market-candles``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from data.connectors._common import async_http_get_json, env_bool, env_str
from utils.async_runner import run_sync

logger = logging.getLogger(__name__)

COMMUNITY_API_URL = "https://community-api.coinmetrics.io/v4"
PRO_API_URL = "https://api.coinmetrics.io/v4"

#: Permanent/empty-result cache keyed by (asset, interval) so unsupported or
#: empty markets are never refetched every cycle (retry-storm prevention).
_EMPTY_CACHE: dict[tuple[str, str], float] = {}
_EMPTY_CACHE_TTL_SECONDS = 12 * 60 * 60
_EMPTY_CACHE_LOCK = None  # single-threaded use; kept simple


def _enabled() -> bool:
    return env_bool("COIN_METRICS_ENABLED", True)


def base_url() -> str:
    mode = env_str("COIN_METRICS_ACCESS_MODE", "community").lower()
    if mode in ("pro", "professional") and env_str("COIN_METRICS_API_KEY"):
        return PRO_API_URL
    return COMMUNITY_API_URL


def _headers() -> dict[str, str]:
    key = env_str("COIN_METRICS_API_KEY")
    return {"Authorization": f"ApiKey {key}"} if key else {}


def _normalize_symbol(symbol: str) -> str:
    s = (symbol or "").upper().strip().replace("/", "").replace("_", "").replace("-", "")
    for suffix in ("USDT", "USDC", "USD", "PERP"):
        if s.endswith(suffix) and len(s) > len(suffix):
            s = s[: -len(suffix)]
            break
    return s


def _map_interval(timeframe: str) -> str:
    return {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "4h": "4h", "1d": "1d",
    }.get((timeframe or "").lower(), "1d")


async def _async_get_candles(
    symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0,
) -> List[Dict[str, Any]]:
    if not _enabled():
        return []
    asset = _normalize_symbol(symbol)
    if not asset:
        return []
    import time as _time

    interval = _map_interval(timeframe)
    cache_key = (asset, interval)
    if cache_key in _EMPTY_CACHE and _EMPTY_CACHE[cache_key] > _time.monotonic():
        return []
    data = await async_http_get_json(
        f"{base_url()}/timeseries/market-candles",
        name="coinmetrics",
        params={
            "markets": f"{asset}-usd-spot",
            "page_size": min(10000, max(1, int(limit or 200))),
            "start_time": "2020-01-01",
        },
        headers=_headers(), timeout=timeout,
    )
    if not isinstance(data, dict):
        return []
    rows = data.get("data") or []
    if not rows:
        # Permanently empty/unsupported market: do not refetch for the TTL.
        _EMPTY_CACHE[cache_key] = _time.monotonic() + _EMPTY_CACHE_TTL_SECONDS
        return []
    out: List[Dict[str, Any]] = []
    for row in rows[-int(limit or 200):]:
        try:
            out.append({
                "timestamp": int(row["time"]),
                "open": float(row["price_open"]),
                "high": float(row["price_high"]),
                "low": float(row["price_low"]),
                "close": float(row["price_close"]),
                "volume": float(row.get("volume", 0) or 0),
            })
        except Exception:
            continue
    return out


def get_candles(
    symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0,
) -> List[Dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit, timeout=timeout))


async def _async_get_network_metric(asset: str, metric: str) -> Optional[Dict[str, Any]]:
    """Community network metric (e.g. ``AdrActCnt``, ``TxCnt``) latest point."""
    if not _enabled():
        return None
    data = await async_http_get_json(
        f"{base_url()}/timeseries/asset-metrics",
        name="coinmetrics",
        params={"assets": _normalize_symbol(asset), "metrics": metric, "page_size": 1},
        headers=_headers(), timeout=8.0,
    )
    if not isinstance(data, dict):
        return None
    rows = data.get("data") or []
    if not rows:
        return None
    return {"asset": _normalize_symbol(asset), "metric": metric, **rows[-1]}


def get_network_metric(asset: str, metric: str) -> Optional[Dict[str, Any]]:
    return run_sync(_async_get_network_metric(asset, metric))


def health() -> Dict[str, Any]:
    mode = env_str("COIN_METRICS_ACCESS_MODE", "community").lower()
    enabled = _enabled()
    return {
        "provider_id": "coinmetrics",
        "enabled": enabled,
        "access_mode": mode,
        "api_url": base_url(),
        "state": "disabled" if not enabled else ("public_ready" if mode == "community" else "configured"),
    }


__all__ = ["base_url", "get_candles", "get_network_metric", "health"]
