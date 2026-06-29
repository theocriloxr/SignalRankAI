"""Economic Calendar & Macro News Protector.

Fetches upcoming high-impact economic events and enforces a 30-minute
no-trade buffer around USD red-folder releases.

Providers (in priority order):
    1. Finnhub  (requires FINNHUB_API_KEY env var — free tier OK)
    2. TradingEconomics  (requires TRADINGECONOMICS_API_KEY — optional)
    3. Static fallback list  (NFP first Friday, CPI 2nd–3rd Wed, FOMC ~8×/year)

Usage::
    from services.economic_calendar import is_no_trade_zone, fetch_economic_events

    if await is_no_trade_zone("EURUSD"):
        return  # skip signal generation
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache — avoid hammering the external APIs every second
# ---------------------------------------------------------------------------
_EVENTS_CACHE: list[dict] = []
_CACHE_FETCHED_AT: Optional[datetime] = None
_CACHE_TTL_SECONDS = 3600  # refresh once per hour

# ---------------------------------------------------------------------------
# Known high-impact USD events (month, day pattern matching)
# Used as a fallback when all APIs are unavailable.
# ---------------------------------------------------------------------------
_FALLBACK_EVENTS: list[dict] = [
    {"title": "Non-Farm Payrolls", "currency": "USD", "impact": "high",
     "description": "First Friday of each month, 13:30 UTC"},
    {"title": "CPI", "currency": "USD", "impact": "high",
     "description": "Usually 2nd–3rd Wednesday, 13:30 UTC"},
    {"title": "FOMC Rate Decision", "currency": "USD", "impact": "high",
     "description": "~8 times per year, 19:00 UTC"},
    {"title": "GDP (Preliminary)", "currency": "USD", "impact": "high",
     "description": "Last Wednesday of month, 13:30 UTC"},
    {"title": "Core PCE Price Index", "currency": "USD", "impact": "high",
     "description": "Last Friday of month, 13:30 UTC"},
]

# Symbols affected by USD macro events
_USD_SENSITIVE_SYMBOLS = {
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD",
    "USDCAD", "XAUUSD", "XAGUSD", "BTCUSD", "BTCUSDT",
    "ETHUSD", "ETHUSDT", "DXY", "US30", "US100", "US500",
}

# Pre-trade buffer: no new signals N minutes before and after a red event
NO_TRADE_BUFFER_MINUTES = int(os.getenv("NO_TRADE_BUFFER_MINUTES", "30"))
REDIS_EVENTS_KEY = "signalrankai:economic_events:v1"
VOLATILITY_BUFFER_MULTIPLIER = float(os.getenv("NEWS_VOLATILITY_BUFFER_MULTIPLIER", "1.0") or 1.0)


async def _load_events_from_redis() -> list[dict]:
    """Load events from the shared Redis cache when available."""
    try:
        from core.redis_state import state

        cached = state.get_sync(REDIS_EVENTS_KEY)
        if cached:
            events = json.loads(cached)
            return events if isinstance(events, list) else []
    except Exception as exc:
        logger.debug("[economic_calendar] Redis cache unavailable: %s", exc)
    return []


async def _load_events_from_db() -> list[dict]:
    """Load upcoming economic events from the DB cache when available."""
    try:
        from db.repository import get_economic_events
        from db.session import get_session, run_with_db_retry

        async def _fetch() -> list[dict]:
            async with get_session() as session:
                events = await get_economic_events(session, hours_ahead=168)
                out = []
                for event in events:
                    impact = str(getattr(event, "impact", "") or "").lower()
                    if impact not in {"high", "medium"}:
                        continue
                    out.append(
                        {
                            "title": getattr(event, "title", ""),
                            "currency": getattr(event, "currency", ""),
                            "impact": impact,
                            "event_time": getattr(event, "event_date", None),
                            "source": getattr(event, "source", None) or "db",
                        }
                    )
                return out

        return await run_with_db_retry(_fetch)
    except Exception as exc:
        logger.debug("[economic_calendar] DB cache unavailable: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Fetch from Finnhub
# ---------------------------------------------------------------------------

async def _fetch_finnhub(from_dt: datetime, to_dt: datetime) -> list[dict]:
    """Fetch economic calendar from Finnhub API.

    Docs: https://finnhub.io/docs/api/economic-calendar
    """
    api_key = os.getenv("FINNHUB_API_KEY", "")
    if not api_key:
        return []
    url = "https://finnhub.io/api/v1/calendar/economic"
    params = {
        "from": from_dt.strftime("%Y-%m-%d"),
        "to": to_dt.strftime("%Y-%m-%d"),
        "token": api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        events = []
        for e in data.get("economicCalendar", []):
            # Finnhub impact: 1=low, 2=medium, 3=high
            impact_raw = int(e.get("impact", 1))
            impact = {1: "low", 2: "medium", 3: "high"}.get(impact_raw, "low")
            if impact != "high":
                continue  # Only gate on red-folder (high) events
            try:
                event_dt = datetime.fromisoformat(e["time"].replace("Z", "+00:00"))
            except Exception:
                continue
            events.append({
                "title": e.get("event", ""),
                "currency": e.get("country", "").upper(),
                "impact": impact,
                "event_time": event_dt,
                "source": "finnhub",
            })
        logger.info(f"[economic_calendar] Finnhub returned {len(events)} high-impact events")
        return events
    except Exception as exc:
        logger.warning(f"[economic_calendar] Finnhub fetch failed: {exc}")
        return []


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

async def fetch_economic_events(force_refresh: bool = False) -> list[dict]:
    """Return a list of upcoming high-impact economic events.

    Results are cached for ``_CACHE_TTL_SECONDS`` seconds.  Pass
    ``force_refresh=True`` to bypass the cache.
    """
    global _EVENTS_CACHE, _CACHE_FETCHED_AT

    now = datetime.now(tz=timezone.utc)
    if (
        not force_refresh
        and _CACHE_FETCHED_AT is not None
        and (now - _CACHE_FETCHED_AT).total_seconds() < _CACHE_TTL_SECONDS
        and _EVENTS_CACHE
    ):
        return _EVENTS_CACHE

    from_dt = now - timedelta(hours=1)
    to_dt = now + timedelta(days=7)

    events = await _load_events_from_redis()
    if events:
        _EVENTS_CACHE = events
        _CACHE_FETCHED_AT = now
        return events

    events = await _load_events_from_db()
    if events:
        _EVENTS_CACHE = events
        _CACHE_FETCHED_AT = now
        return events

    events = await _fetch_finnhub(from_dt, to_dt)

    if not events:
        logger.warning(
            "[economic_calendar] All API providers failed; using fallback static list"
        )
        # Emit a synthetic "unknown time" warning record so engine can still
        # see there are events — callers check is_no_trade_zone() which will
        # gracefully return False for events without event_time.
        events = [
            {**e, "event_time": None, "source": "fallback"}
            for e in _FALLBACK_EVENTS
        ]

    _EVENTS_CACHE = events
    _CACHE_FETCHED_AT = now
    logger.info(f"[economic_calendar] Cache refreshed: {len(events)} events")
    return events


async def is_no_trade_zone(
    symbol: str,
    dt: Optional[datetime] = None,
    buffer_minutes: int = NO_TRADE_BUFFER_MINUTES,
) -> bool:
    """Return True if ``symbol`` is within the no-trade buffer around a high-impact event.

    Only applies to symbols in ``_USD_SENSITIVE_SYMBOLS``.  The buffer window is
    [event_time - buffer_minutes, event_time + buffer_minutes].

    Args:
        symbol:         Canonical symbol (e.g. ``"EURUSD"``).
        dt:             The datetime to check.  Defaults to ``now(UTC)``.
        buffer_minutes: Override the buffer window.  Defaults to env
                        ``NO_TRADE_BUFFER_MINUTES`` (30).
    """
    if str(symbol).upper() not in _USD_SENSITIVE_SYMBOLS:
        return False

    now = dt or datetime.now(tz=timezone.utc)
    events = await fetch_economic_events()

    for event in events:
        if event.get("currency") != "USD":
            continue
        if event.get("impact") != "high":
            continue
        event_time: Optional[datetime] = event.get("event_time")
        if event_time is None:
            continue
        # Make sure both datetimes are timezone-aware
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)
        delta = abs((now - event_time).total_seconds())
        if delta <= buffer_minutes * 60:
            logger.warning(
                f"[economic_calendar] NO-TRADE ZONE: {symbol} is within {buffer_minutes}min"
                f" of '{event['title']}' at {event_time.isoformat()} "
                f"(Δ={delta:.0f}s)"
            )
            return True
    return False


async def get_macro_news_context(now: Optional[datetime] = None) -> dict[str, object]:
    """Return macro-news timing features for ML and gating.

    Exposes the latest and next high-impact USD event in minutes, plus a
    normalized pressure score that can be fed into score calibration and ML.
    """
    ref_now = now or datetime.now(tz=timezone.utc)
    events = await fetch_economic_events()
    closest_past: Optional[dict] = None
    closest_future: Optional[dict] = None
    past_delta_min: Optional[float] = None
    future_delta_min: Optional[float] = None

    for event in events:
        if event.get("currency") != "USD" or event.get("impact") != "high":
            continue
        event_time: Optional[datetime] = event.get("event_time")
        if event_time is None:
            continue
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)
        delta_min = (ref_now - event_time).total_seconds() / 60.0
        if delta_min >= 0:
            if past_delta_min is None or delta_min < past_delta_min:
                past_delta_min = delta_min
                closest_past = event
        else:
            future_min = abs(delta_min)
            if future_delta_min is None or future_min < future_delta_min:
                future_delta_min = future_min
                closest_future = event

    buffer_min = max(1.0, float(NO_TRADE_BUFFER_MINUTES))
    pressure = 0.0
    if future_delta_min is not None:
        pressure = max(pressure, max(0.0, 1.0 - (future_delta_min / buffer_min)))
    if past_delta_min is not None:
        pressure = max(pressure, max(0.0, 1.0 - (past_delta_min / buffer_min)))

    return {
        "minutes_since_high_impact_news": float(past_delta_min) if past_delta_min is not None else None,
        "minutes_until_high_impact_news": float(future_delta_min) if future_delta_min is not None else None,
        "last_high_impact_news_title": str((closest_past or {}).get("title") or "") if closest_past else "",
        "next_high_impact_news_title": str((closest_future or {}).get("title") or "") if closest_future else "",
        "news_event_impact_score": float(max(0.0, min(1.0, pressure))),
    }


def is_no_trade_zone_sync(
    symbol: str,
    dt: Optional[datetime] = None,
    buffer_minutes: int = NO_TRADE_BUFFER_MINUTES,
) -> bool:
    """Synchronous wrapper for ``is_no_trade_zone`` — safe to call from sync code."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    is_no_trade_zone(symbol, dt, buffer_minutes),
                )
                return future.result(timeout=6.0)
        else:
            return loop.run_until_complete(is_no_trade_zone(symbol, dt, buffer_minutes))
    except Exception:
        return False


async def get_upcoming_events_summary(hours_ahead: int = 24) -> str:
    """Return a human-readable summary of upcoming high-impact events.

    Suitable for appending to signal messages or bot admin reports.
    """
    events = await fetch_economic_events()
    now = datetime.now(tz=timezone.utc)
    cutoff = now + timedelta(hours=hours_ahead)
    upcoming = []
    for e in events:
        et = e.get("event_time")
        if et is None:
            continue
        if et.tzinfo is None:
            et = et.replace(tzinfo=timezone.utc)
        if now <= et <= cutoff:
            upcoming.append(e)

    if not upcoming:
        return ""

    lines = ["⚠️ <b>Upcoming High-Impact Events</b>"]
    for e in sorted(upcoming, key=lambda x: x["event_time"]):
        et = e["event_time"]
        lines.append(f"  • {e['title']} ({e['currency']}) — {et.strftime('%d %b %H:%M')} UTC")
    return "\n".join(lines)


async def get_volatility_buffer_info() -> dict:
    """Return SL/position adjustments for current high-impact news windows."""
    if VOLATILITY_BUFFER_MULTIPLIER <= 1.0:
        return {"active": False, "sl_multiplier": 1.0, "position_reducer": 1.0, "event": None}
    now = datetime.now(tz=timezone.utc)
    events = await fetch_economic_events()
    for event in events:
        if event.get("currency") != "USD" or event.get("impact") != "high":
            continue
        event_time = event.get("event_time")
        if event_time is None:
            continue
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)
        if abs((now - event_time).total_seconds()) <= NO_TRADE_BUFFER_MINUTES * 60:
            return {
                "active": True,
                "sl_multiplier": VOLATILITY_BUFFER_MULTIPLIER,
                "position_reducer": 1.0 / VOLATILITY_BUFFER_MULTIPLIER,
                "event": event,
            }
    return {"active": False, "sl_multiplier": 1.0, "position_reducer": 1.0, "event": None}
