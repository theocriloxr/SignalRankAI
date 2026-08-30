"""CoinGlass adapter (aggregated perpetual market intelligence).

Role (provider addendum §19): funding rates, open interest, liquidations,
long/short ratios, order-book analytics.  Capabilities must reflect the
actually subscribed plan; heatmaps/options stay off by default.

Dormant-by-default: without ``COINGLASS_API_KEY`` returns ``None`` and reports
``missing_credentials``.  Never fills logs with exceptions.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from data.connectors._common import async_http_get_json, env_bool, env_str
from utils.async_runner import run_sync

logger = logging.getLogger(__name__)

API_URL = "https://open-api-v4.coinglass.com"


def _enabled() -> bool:
    return env_bool("COINGLASS_ENABLED", False)


def _api_key() -> str:
    return env_str("COINGLASS_API_KEY")


def _headers() -> dict[str, str]:
    key = _api_key()
    return {"CG-API-KEY": key} if key else {}


async def _async_get(path: str, params: dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _enabled() or not _api_key():
        return None
    data = await async_http_get_json(
        f"{API_URL}{path}", name="coinglass", params=params, headers=_headers(), timeout=10.0
    )
    if not isinstance(data, dict):
        return None
    return data


async def _async_funding(symbol: str) -> Optional[Dict[str, Any]]:
    """Current funding rate + predicted funding for a perp symbol."""
    data = await _async_get("/api/funding-rate/current", {"symbol": str(symbol).upper(), "interval": "8h"})
    return data


def get_funding(symbol: str) -> Optional[Dict[str, Any]]:
    return run_sync(_async_funding(symbol))


async def _async_open_interest(symbol: str) -> Optional[Dict[str, Any]]:
    data = await _async_get("/api/futures/open-interest/exchange", {"symbol": str(symbol).upper()})
    return data


def get_open_interest(symbol: str) -> Optional[Dict[str, Any]]:
    return run_sync(_async_open_interest(symbol))


async def _async_liquidations(symbol: str) -> Optional[Dict[str, Any]]:
    data = await _async_get("/api/futures/liquidation/v2", {"symbol": str(symbol).upper(), "type": "2"})
    return data


def get_liquidations(symbol: str) -> Optional[Dict[str, Any]]:
    return run_sync(_async_liquidations(symbol))


def health() -> Dict[str, Any]:
    enabled = _enabled()
    has_key = bool(_api_key())
    return {
        "provider_id": "coinglass",
        "enabled": enabled,
        "state": (
            "disabled" if not enabled
            else ("healthy" if has_key else "missing_credentials")
        ),
        "required_env": ("COINGLASS_API_KEY",),
        "api_url": API_URL,
        "capabilities": {
            "funding": env_bool("COINGLASS_FUNDING_ENABLED", True),
            "open_interest": env_bool("COINGLASS_OPEN_INTEREST_ENABLED", True),
            "liquidations": env_bool("COINGLASS_LIQUIDATIONS_ENABLED", True),
            "long_short": env_bool("COINGLASS_LONG_SHORT_ENABLED", True),
            "orderbook": env_bool("COINGLASS_ORDERBOOK_ENABLED", False),
            "options": env_bool("COINGLASS_OPTIONS_ENABLED", False),
            "heatmap": env_bool("COINGLASS_HEATMAP_ENABLED", False),
        },
    }


__all__ = ["API_URL", "get_funding", "get_liquidations", "get_open_interest", "health"]
