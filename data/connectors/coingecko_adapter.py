"""CoinGecko / GeckoTerminal adapter (public, keyless market data + discovery).

Roles (provider addendum §15):
* dynamic token/metadata discovery (``/coins/markets``, GeckoTerminal pools)
* market context and last-resort candle fallback
* NEVER used as the final execution quote (``COINGECKO_USE_FOR_EXECUTION_QUOTE=0``)

Public endpoints work without a key.  A demo/pro API key upgrades the base URL
and rate budget.  A cooldown guard prevents retry storms against the free tier.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from data.connectors._common import async_http_get_json, env_bool, env_str
from utils.async_runner import run_sync

logger = logging.getLogger(__name__)

PUBLIC_API_URL = "https://api.coingecko.com/api/v3"
PRO_API_URL = "https://pro-api.coingecko.com/api/v3"
GECKOTERMINAL_API_URL = "https://api.geckoterminal.com/api/v2"

_COOLDOWN_UNTIL: dict[str, float] = {}
_COOLDOWN_SECONDS = 45.0  # free tier is ~10-30 req/min; stay far below
_ID_CACHE: dict[str, str] = {}


def _enabled() -> bool:
    return env_bool("COINGECKO_ENABLED", True)


def _cooldown_active() -> bool:
    return _COOLDOWN_UNTIL.get("coingecko", 0.0) > time.monotonic()


def _mark_cooldown() -> None:
    _COOLDOWN_UNTIL["coingecko"] = time.monotonic() + _COOLDOWN_SECONDS


def base_url() -> str:
    access_mode = env_str("COINGECKO_ACCESS_MODE", "keyless").lower()
    if access_mode == "pro" and env_str("COINGECKO_PRO_API_KEY"):
        return PRO_API_URL
    return PUBLIC_API_URL


def _headers() -> dict[str, str]:
    key = env_str("COINGECKO_PRO_API_KEY") or env_str("COINGECKO_DEMO_API_KEY")
    return {"x-cg-pro-api-key": key} if key else {}


def _symbol_to_id_cache() -> dict[str, str]:
    # Private symbol->id cache keeps this adapter self-contained; the legacy
    # cache in data.providers is untouched.
    return _ID_CACHE


async def _async_resolve_id(symbol: str) -> Optional[str]:
    key = str(symbol or "").upper().strip()
    cache = _symbol_to_id_cache()
    if key in cache:
        # "" marks a permanently unsupported symbol (never retried this process).
        return cache[key] or None
    if _cooldown_active():
        return None
    # Try /coins/markets?ids=... only for exact coin IDs later; first search list.
    data = await async_http_get_json(
        f"{base_url()}/coins/list", name="coingecko", headers=_headers(), timeout=6.0
    )
    if not isinstance(data, list):
        _mark_cooldown()
        return None
    normalized = key.replace("/", "").replace("_", "").replace("-", "")
    for item in data:
        cg_symbol = str(item.get("symbol") or "").upper().strip()
        cg_id = str(item.get("id") or "").strip()
        if cg_symbol == key or cg_symbol == normalized or key.lower() == cg_id:
            cache[key] = cg_id
            return cg_id
    # Permanently unsupported symbol: cache the negative result to prevent
    # retry storms (provider addendum §15 requirement).
    cache[key] = ""
    _mark_cooldown()
    return None


async def _async_get_candles(
    symbol: str, timeframe: str, limit: int = 200, timeout: float = 8.0
) -> List[Dict[str, Any]]:
    if not _enabled() or _cooldown_active():
        return []
    tf = (timeframe or "1h").lower()
    # Fail-closed granularity: the free API only honestly serves 1h (hourly
    # market_chart) and 1d (ohlc). Anything finer would return mislabelled
    # daily/hourly bars, so it is rejected instead (truthfulness rule).
    if tf not in ("1h", "1d"):
        return []
    coin_id = await _async_resolve_id(symbol)
    if not coin_id:
        return []
    if tf == "1d":
        data = await async_http_get_json(
            f"{base_url()}/coins/{coin_id}/ohlc",
            name="coingecko", params={"vs_currency": "usd", "days": 30},
            headers=_headers(), timeout=timeout,
        )
        if not isinstance(data, list):
            return []
        out: List[Dict[str, Any]] = []
        for row in data[-int(limit or 200):]:
            try:
                ts_ms, o, h, l, c = row
                out.append({
                    "timestamp": int(ts_ms) // 1000,
                    "open": float(o), "high": float(h), "low": float(l), "close": float(c),
                    "volume": 0.0,
                })
            except Exception:
                continue
        return out
    data = await async_http_get_json(
        f"{base_url()}/coins/{coin_id}/market_chart",
        name="coingecko",
        params={"vs_currency": "usd", "days": 7, "interval": "hourly"},
        headers=_headers(), timeout=timeout,
    )
    if not isinstance(data, dict):
        return []
    prices = data.get("prices") or []
    out = []
    for row in prices[-int(limit or 200):]:
        try:
            ts_ms, price = row
            out.append({
                "timestamp": int(ts_ms) // 1000,
                "open": float(price), "high": float(price),
                "low": float(price), "close": float(price), "volume": 0.0,
            })
        except Exception:
            continue
    return out


def get_candles(
    symbol: str, timeframe: str, limit: int = 200, timeout: float = 10.0
) -> List[Dict[str, Any]]:
    return run_sync(_async_get_candles(symbol, timeframe, limit=limit, timeout=timeout))


async def _async_get_price(symbol: str) -> Optional[float]:
    """Keyless spot reference price (context only — never execution truth)."""
    if not _enabled() or _cooldown_active():
        return None
    coin_id = await _async_resolve_id(symbol)
    if not coin_id:
        return None
    data = await async_http_get_json(
        f"{base_url()}/simple/price",
        name="coingecko",
        params={"ids": coin_id, "vs_currencies": "usd"},
        headers=_headers(), timeout=6.0,
    )
    if not isinstance(data, dict):
        return None
    try:
        return float(data[coin_id]["usd"])
    except Exception:
        return None


def get_price(symbol: str) -> Optional[float]:
    return run_sync(_async_get_price(symbol))


async def _async_discover_instruments(
    *, top: int = 100, active_only: bool = True,
) -> List[Dict[str, Any]]:
    """Discovery: top crypto tokens by market cap via public /coins/markets."""
    if not _enabled() or _cooldown_active():
        return []
    data = await async_http_get_json(
        f"{base_url()}/coins/markets",
        name="coingecko",
        params={"vs_currency": "usd", "order": "market_cap_desc", "per_page": min(250, max(1, top)), "page": 1},
        headers=_headers(), timeout=10.0,
    )
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        try:
            symbol = str(item.get("symbol") or "").upper().strip()
            if not symbol:
                continue
            status = "active" if active_only else str(item.get("status") or "active")
            out.append({
                "provider": "coingecko",
                "venue": "coingecko",
                "provider_symbol": f"{symbol}USDT",
                "asset_class": "crypto",
                "instrument_type": "spot",
                "base": symbol,
                "quote": "USDT",
                "market_status": status,
                "metadata": {
                    "coingecko_id": item.get("id"),
                    "market_cap_usd": item.get("market_cap"),
                    "total_volume_usd": item.get("total_volume"),
                    "source": "coins_markets",
                },
            })
        except Exception:
            continue
    return out


def discover_instruments(*, top: int = 100, active_only: bool = True) -> List[Dict[str, Any]]:
    return run_sync(_async_discover_instruments(top=top, active_only=active_only))


def health() -> Dict[str, Any]:
    """Zero-network health probe: env gate + endpoint selection only."""
    enabled = _enabled()
    mode = env_str("COINGECKO_ACCESS_MODE", "keyless")
    return {
        "provider_id": "coingecko",
        "enabled": enabled,
        "access_mode": mode,
        "api_url": base_url(),
        "state": "disabled" if not enabled else ("public_ready" if mode == "keyless" else "configured"),
        "use_for_execution_quote": env_bool("COINGECKO_USE_FOR_EXECUTION_QUOTE", False),
    }


__all__ = ["base_url", "discover_instruments", "get_candles", "get_price", "health"]
