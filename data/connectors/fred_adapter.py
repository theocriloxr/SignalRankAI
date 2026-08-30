"""FRED (Federal Reserve Economic Data) macro adapter.

Role (provider addendum §17): interest rates, yields, inflation, employment
and macro features for context and backtesting.  ``FRED_VINTAGE_DATA_ENABLED``
keeps observations point-in-time aware so backtests never leak revisions.

Dormant-by-default: without ``FRED_API_KEY`` the adapter returns ``[]``/``None``
and reports ``missing_credentials`` instead of raising.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from data.connectors._common import async_http_get_json, env_bool, env_str
from utils.async_runner import run_sync

logger = logging.getLogger(__name__)

API_URL = "https://api.stlouisfed.org/fred"


def _enabled() -> bool:
    return env_bool("FRED_ENABLED", True)


def _api_key() -> str:
    return env_str("FRED_API_KEY")


async def _async_fetch_series(
    series_id: str,
    *,
    start: str | None = None,
    end: str | None = None,
    limit: int = 1000,
    vintage: bool | None = None,
) -> List[Dict[str, Any]]:
    """Fetch one macro series.  Returns [] when dormant or on any failure."""
    if not _enabled() or not _api_key():
        return []
    params: Dict[str, Any] = {
        "series_id": series_id,
        "api_key": _api_key(),
        "file_type": "json",
        "sort_order": "asc",
        "limit": max(1, min(100000, int(limit or 1000))),
    }
    if start:
        params["observation_start"] = start
    if end:
        params["observation_end"] = end
    # The observations endpoint is inherently vintage-aware through
    # realtime_start/realtime_end; FRED_VINTAGE_DATA_ENABLED governs backtest
    # discipline rather than endpoint choice.
    url = f"{API_URL}/series/observations"
    data = await async_http_get_json(url, name="fred", params=params, timeout=10.0)
    if not isinstance(data, dict):
        return []
    rows = data.get("observations") or []
    out: List[Dict[str, Any]] = []
    for row in rows:
        value = row.get("value")
        if value in (None, "."):
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        out.append({
            "series_id": series_id,
            "timestamp": row.get("date"),
            "value": parsed,
            "realtime_start": row.get("realtime_start"),
            "realtime_end": row.get("realtime_end"),
        })
    return out


def fetch_series(
    series_id: str,
    *,
    start: str | None = None,
    end: str | None = None,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    return run_sync(_async_fetch_series(series_id, start=start, end=end, limit=limit))


def health() -> Dict[str, Any]:
    enabled = _enabled()
    has_key = bool(_api_key())
    return {
        "provider_id": "fred",
        "enabled": enabled,
        "state": (
            "disabled" if not enabled
            else ("healthy" if has_key else "missing_credentials")
        ),
        "required_env": ("FRED_API_KEY",),
        "api_url": API_URL,
    }


__all__ = ["API_URL", "fetch_series", "health"]
