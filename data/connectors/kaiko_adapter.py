"""Kaiko adapter (institutional normalized crypto market data).

Role (provider addendum §20): normalized trades, order books, derivatives
reference data, fair-market values and versioned datasets for institutional
users.  Regional endpoints follow ``KAIKO_REGION``.

Dormant-by-default: without ``KAIKO_API_KEY`` returns ``None`` and reports
``missing_credentials``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from data.connectors._common import async_http_get_json, env_bool, env_str
from utils.async_runner import run_sync

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "https://us.market-api.kaiko.io"


def _enabled() -> bool:
    return env_bool("KAIKO_ENABLED", False)


def _api_key() -> str:
    return env_str("KAIKO_API_KEY")


def api_url() -> str:
    return env_str("KAIKO_API_URL") or DEFAULT_API_URL


def _headers() -> dict[str, str]:
    key = _api_key()
    return {"X-Api-Key": key} if key else {}


async def _async_reference_data() -> Optional[Dict[str, Any]]:
    """Instrument reference-data coverage (venues, asset classes)."""
    if not _enabled() or not _api_key():
        return None
    data = await async_http_get_json(
        f"{api_url()}/v2/reference/exchanges",
        name="kaiko", headers=_headers(), timeout=10.0,
    )
    if not isinstance(data, dict):
        return None
    return data


def reference_data() -> Optional[Dict[str, Any]]:
    return run_sync(_async_reference_data())


async def _async_ohlcv(exchange: str, pair: str) -> Optional[Dict[str, Any]]:
    """Latest OHLCV tick for one institutional market."""
    if not _enabled() or not _api_key():
        return None
    data = await async_http_get_json(
        f"{api_url()}/v2/data/trades.v1/spot_exchange_rate/{exchange}/{pair}",
        name="kaiko", headers=_headers(), timeout=10.0,
    )
    if not isinstance(data, dict):
        return None
    return data


def get_ohlcv(exchange: str, pair: str) -> Optional[Dict[str, Any]]:
    return run_sync(_async_ohlcv(exchange, pair))


def health() -> Dict[str, Any]:
    enabled = _enabled()
    has_key = bool(_api_key())
    return {
        "provider_id": "kaiko",
        "enabled": enabled,
        "state": (
            "disabled" if not enabled
            else ("healthy" if has_key else "missing_credentials")
        ),
        "required_env": ("KAIKO_API_KEY",),
        "api_url": api_url(),
        "region": env_str("KAIKO_REGION", "us"),
    }


__all__ = ["api_url", "get_ohlcv", "health", "reference_data"]
