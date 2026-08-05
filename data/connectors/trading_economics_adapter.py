"""Trading Economics adapter (economic calendar + indicator context).

Role (provider addendum §18): consensus-vs-actual releases, economic
indicators, bond yields, commodity prices and earnings calendars.
``TRADING_ECONOMICS_POINT_IN_TIME_ENABLED`` gates point-in-time history.

Dormant-by-default: without ``TRADING_ECONOMICS_API_KEY`` returns ``[]``/``None``
and reports ``missing_credentials``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from data.connectors._common import async_http_get_json, env_bool, env_str
from utils.async_runner import run_sync

logger = logging.getLogger(__name__)

API_URL = "https://api.tradingeconomics.com"


def _enabled() -> bool:
    return env_bool("TRADING_ECONOMICS_ENABLED", False)


def _api_key() -> str:
    return env_str("TRADING_ECONOMICS_API_KEY")


async def _async_fetch_calendar(
    *,
    country: str = "",
    since: str | None = None,
    until: str | None = None,
) -> List[Dict[str, Any]]:
    if not _enabled() or not _api_key():
        return []
    path = f"/calendar/country/{country}" if country else "/calendar"
    data = await async_http_get_json(
        f"{API_URL}{path}",
        name="trading_economics",
        params={"c": _api_key(), **({"d1": since, "d2": until} if since and until else {})},
        timeout=10.0,
    )
    if not isinstance(data, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in data:
        try:
            out.append({
                "country": item.get("Country"),
                "category": item.get("Category"),
                "event": item.get("Event"),
                "timestamp": item.get("Date"),
                "actual": item.get("Actual"),
                "previous": item.get("Previous"),
                "forecast": item.get("Forecast"),
            })
        except Exception:
            continue
    return out


def fetch_calendar(*, country: str = "", since: str | None = None, until: str | None = None) -> List[Dict[str, Any]]:
    return run_sync(_async_fetch_calendar(country=country, since=since, until=until))


def health() -> Dict[str, Any]:
    enabled = _enabled()
    has_key = bool(_api_key())
    return {
        "provider_id": "trading_economics",
        "enabled": enabled,
        "state": (
            "disabled" if not enabled
            else ("healthy" if has_key else "missing_credentials")
        ),
        "required_env": ("TRADING_ECONOMICS_API_KEY",),
        "api_url": API_URL,
    }


__all__ = ["API_URL", "fetch_calendar", "health"]
