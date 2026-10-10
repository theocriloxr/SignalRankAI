"""FRED (Federal Reserve Economic Data) macro adapter.

Role (provider addendum §17): interest rates, yields, inflation, employment
and macro features for context and backtesting. ``FRED_VINTAGE_DATA_ENABLED``
requires an explicit historical as_of date; it cannot turn latest revisions
into historical data. FRED vintages have day precision, not intraday release
timestamps. Replay still needs independently qualified release availability.

Dormant-by-default: without ``FRED_API_KEY`` the adapter returns ``[]``/``None``
and reports ``missing_credentials`` instead of raising.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List

from data.connectors._common import async_http_get_json, env_bool, env_str
from utils.async_runner import run_sync

logger = logging.getLogger(__name__)

API_URL = "https://api.stlouisfed.org/fred"


def _enabled() -> bool:
    return env_bool("FRED_ENABLED", False)


def _api_key() -> str:
    return env_str("FRED_API_KEY")


def _date(value: Any) -> date | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


async def _async_fetch_series(
    series_id: str,
    *,
    start: str | None = None,
    end: str | None = None,
    limit: int = 1000,
    vintage: bool | None = None,
    as_of: str | None = None,
) -> List[Dict[str, Any]]:
    """Fetch one macro series.  Returns [] when dormant or on any failure."""
    if not _enabled() or not _api_key():
        return []
    cutoff = _date(as_of) if as_of is not None else None
    vintage_required = env_bool("FRED_VINTAGE_DATA_ENABLED", False) or vintage is True
    if (as_of is not None and cutoff is None) or (vintage_required and cutoff is None):
        logger.warning("fred historical data unavailable: explicit valid as_of date required")
        return []
    if cutoff is not None and cutoff > datetime.now(timezone.utc).date():
        logger.warning("fred historical data unavailable: future vintage requested")
        return []
    if (start is not None and _date(start) is None) or (end is not None and _date(end) is None):
        return []
    effective_end = min(end, cutoff.isoformat()) if end and cutoff else cutoff.isoformat() if cutoff else end
    if start and effective_end and start > effective_end:
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
    if effective_end:
        params["observation_end"] = effective_end
    if cutoff is not None:
        # Both inclusive bounds must be pinned. observation_end alone limits
        # economic periods and still returns today's revisions by default.
        params.update(realtime_start=cutoff.isoformat(), realtime_end=cutoff.isoformat())
    url = f"{API_URL}/series/observations"
    data = await async_http_get_json(url, name="fred", params=params, timeout=10.0)
    if not isinstance(data, dict):
        return []
    rows = data.get("observations")
    if not isinstance(rows, list) or len(rows) > params["limit"]:
        return []
    if cutoff is not None and (data.get("realtime_start") != as_of or data.get("realtime_end") != as_of):
        logger.warning("fred historical data unavailable: response vintage mismatch")
        return []
    captured_at = datetime.now(timezone.utc).isoformat()
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            return []
        if cutoff is not None:
            observed, first, last = (_date(row.get(key)) for key in ("date", "realtime_start", "realtime_end"))
            if observed is None or first is None or last is None or observed > cutoff or not first <= cutoff <= last:
                logger.warning("fred historical data unavailable: observation outside requested vintage")
                return []
        value = row.get("value")
        if value in (None, "."):
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(parsed):
            continue
        out.append(
            {
                "series_id": series_id,
                "timestamp": row.get("date"),
                "value": parsed,
                "realtime_start": row.get("realtime_start"),
                "realtime_end": row.get("realtime_end"),
                "provider": "fred",
                "captured_at": captured_at,
                "as_of_date": as_of,
                "revision_mode": "date_vintage" if cutoff else "latest_revisions",
                "availability_precision": "day" if cutoff else "unverified",
                "intraday_availability_verified": False,
            }
        )
    return out


def fetch_series(
    series_id: str,
    *,
    start: str | None = None,
    end: str | None = None,
    limit: int = 1000,
    vintage: bool | None = None,
    as_of: str | None = None,
) -> List[Dict[str, Any]]:
    """Pin revisions with YYYY-MM-DD as_of; dates alone cannot certify intraday use."""
    return run_sync(_async_fetch_series(series_id, start=start, end=end, limit=limit, vintage=vintage, as_of=as_of))


def health() -> Dict[str, Any]:
    enabled = _enabled()
    has_key = bool(_api_key())
    return {
        "provider_id": "fred",
        "enabled": enabled,
        "state": ("disabled" if not enabled else ("healthy" if has_key else "missing_credentials")),
        "required_env": ("FRED_API_KEY",),
        "api_url": API_URL,
    }


__all__ = ["API_URL", "fetch_series", "health"]
