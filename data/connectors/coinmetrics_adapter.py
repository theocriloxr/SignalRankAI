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
from datetime import datetime, timedelta, timezone
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


def _market_candidates(symbol: str, asset: str) -> tuple[str, ...]:
    raw = str(symbol or "").upper().replace("/", "").replace("_", "").replace("-", "")
    quote = "usdt" if raw.endswith("USDT") else "usd"
    base = asset.lower()
    ordered = [
        f"binance-{base}-{quote}-spot",
        f"coinbase-{base}-usd-spot",
        f"kraken-{base}-usd-spot",
    ]
    return tuple(dict.fromkeys(ordered))


def _pair_candidate(symbol: str, asset: str) -> str:
    raw = str(symbol or "").upper().replace("/", "").replace("_", "").replace("-", "")
    # Community pair candles have broader historical coverage for BTC/USD than
    # venue-specific USDT markets. This provider is historical/context-only, so
    # USD aggregation is an honest fallback for USDT/USDC-labelled inputs.
    quote = "usd"
    if raw.endswith("EUR"):
        quote = "eur"
    elif raw.endswith("GBP"):
        quote = "gbp"
    return f"{asset.lower()}-{quote}"


def _timestamp_ms(value: Any) -> int:
    if isinstance(value, (int, float)):
        numeric = int(value)
        return numeric if numeric > 10_000_000_000 else numeric * 1000
    text = str(value or "").strip()
    if text.isdigit():
        numeric = int(text)
        return numeric if numeric > 10_000_000_000 else numeric * 1000
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _lookback_start(interval: str, limit: int) -> str:
    minutes = {
        "1m": 1, "5m": 5, "15m": 15, "30m": 30,
        "1h": 60, "4h": 240, "1d": 1440,
    }.get(interval, 1440)
    days = max(7, int((max(2, int(limit)) * minutes) / 1440) + 7)
    return (datetime.now(timezone.utc) - timedelta(days=min(3650, days))).isoformat()


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
    rows: list[dict[str, Any]] = []
    for market in _market_candidates(symbol, asset):
        data = await async_http_get_json(
            f"{base_url()}/timeseries/market-candles",
            name="coinmetrics",
            params={
                "markets": market,
                "frequency": interval,
                "page_size": min(10000, max(2, int(limit or 200))),
                "start_time": _lookback_start(interval, int(limit or 200)),
                "end_time": datetime.now(timezone.utc).isoformat(),
                "paging_from": "end",
            },
            headers=_headers(), timeout=timeout,
        )
        if isinstance(data, dict) and isinstance(data.get("data"), list) and data.get("data"):
            rows = list(data["data"])
            break

    # The Community API may not expose a recent venue-specific market even when
    # its aggregated pair history is available. Pair candles are an honest
    # historical/context fallback and are never used as an execution quote.
    if not rows:
        pair = _pair_candidate(symbol, asset)
        data = await async_http_get_json(
            f"{base_url()}/timeseries/pair-candles",
            name="coinmetrics",
            params={
                "pairs": pair,
                "frequency": interval,
                "page_size": min(10000, max(2, int(limit or 200))),
                "paging_from": "end",
            },
            headers=_headers(), timeout=timeout,
        )
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            rows = list(data.get("data") or [])

    if not rows:
        # Empty/unsupported market: avoid repeatedly hammering the public API.
        _EMPTY_CACHE[cache_key] = _time.monotonic() + _EMPTY_CACHE_TTL_SECONDS
        return []
    out: List[Dict[str, Any]] = []
    for row in rows[-int(limit or 200):]:
        try:
            out.append({
                "timestamp": _timestamp_ms(row["time"]),
                "open": float(row["price_open"]),
                "high": float(row["price_high"]),
                "low": float(row["price_low"]),
                "close": float(row["price_close"]),
                "volume": float(row.get("volume", 0) or 0),
            })
        except Exception:
            continue
    out.sort(key=lambda item: int(item.get("timestamp") or 0))
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
