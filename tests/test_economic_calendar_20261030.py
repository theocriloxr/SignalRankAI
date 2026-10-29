"""Economic calendar and news blackout (30 Oct 2026).

Bugs these tests pin:
- the engine runs its loop in an executor thread, where the old sync wrapper's
  asyncio.get_event_loop() raised and was swallowed, so the blackout never applied;
- one failed feed fetch cached the timeless fallback in Redis for an hour,
  disabling news protection in every process;
- the news sync worker read ``event_date`` while events carry ``event_time``,
  so nothing reached the database cache, and it compared aware with naive times;
- the database cache dropped just-past events, losing the post-release blackout;
- ``EUR/USD``-style symbols were not recognised.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url

from services import economic_calendar as ec

NOW = datetime(2026, 10, 30, 12, 30, tzinfo=timezone.utc)


def _event(minutes_from_now: float, *, currency="USD", impact="high", title="CPI", base=NOW, naive=False):
    when = base + timedelta(minutes=minutes_from_now)
    return {"title": title, "currency": currency, "impact": impact,
            "event_time": when.replace(tzinfo=None) if naive else when, "source": "test"}


@pytest.fixture
def events(monkeypatch):
    holder: list[dict] = []

    async def fake_fetch(force_refresh: bool = False):
        return holder

    monkeypatch.setattr(ec, "fetch_economic_events", fake_fetch)
    return holder


@pytest.fixture
def mock_http(monkeypatch):
    real = httpx.AsyncClient
    routes: dict[str, httpx.Response] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        for prefix, response in routes.items():
            if str(request.url).startswith(prefix):
                return response
        return httpx.Response(404)

    monkeypatch.setattr(ec.httpx, "AsyncClient",
                        lambda *a, **k: real(*a, transport=httpx.MockTransport(handler), **k))
    return routes


# --- Feed parsing -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_forex_factory_times_are_converted_to_utc_across_dst(mock_http):
    mock_http[ec._FOREX_FACTORY_URL] = httpx.Response(200, json=[
        {"title": "CPI m/m", "country": "USD", "date": "2026-10-30T08:30:00-04:00", "impact": "High"},  # EDT
        {"title": "Non-Farm Employment Change", "country": "USD", "date": "2026-11-06T08:30:00-05:00", "impact": "High"},  # EST
        {"title": "Retail Sales", "country": "USD", "date": "2026-10-31T08:30:00-04:00", "impact": "Medium"},
        {"title": "Bank Holiday", "country": "USD", "date": "2026-10-31T00:00:00-04:00", "impact": "Low"},
        {"title": "Tentative", "country": "USD", "date": "tbd", "impact": "High"},
        {"title": "Too late", "country": "USD", "date": "2026-12-01T08:30:00-05:00", "impact": "High"},
    ])
    out = await ec._fetch_forex_factory(NOW - timedelta(hours=1), NOW + timedelta(days=8))
    times = {e["title"]: e["event_time"] for e in out}
    assert times == {"CPI m/m": datetime(2026, 10, 30, 12, 30, tzinfo=timezone.utc),
                     "Non-Farm Employment Change": datetime(2026, 11, 6, 13, 30, tzinfo=timezone.utc),
                     "Retail Sales": datetime(2026, 10, 31, 12, 30, tzinfo=timezone.utc)}
    assert {e["impact"] for e in out} == {"high", "medium"}


@pytest.mark.asyncio
async def test_finnhub_keeps_high_impact_only_and_never_logs_its_token(mock_http, monkeypatch, caplog):
    monkeypatch.setenv("FINNHUB_API_KEY", "fh_secret_token_value")
    mock_http["https://finnhub.io/api/v1/calendar/economic"] = httpx.Response(200, json={"economicCalendar": [
        {"event": "FOMC", "country": "us", "impact": 3, "time": "2026-11-04T18:00:00Z"},
        {"event": "Claims", "country": "us", "impact": 2, "time": "2026-11-05T12:30:00Z"},
    ]})
    out = await ec._fetch_finnhub(NOW, NOW + timedelta(days=7))
    assert [(e["title"], e["currency"], e["event_time"]) for e in out] == [
        ("FOMC", "US", datetime(2026, 11, 4, 18, 0, tzinfo=timezone.utc))]
    mock_http["https://finnhub.io/api/v1/calendar/economic"] = httpx.Response(500)
    caplog.set_level("WARNING")
    assert await ec._fetch_finnhub(NOW, NOW + timedelta(days=7)) == []
    assert "fh_secret_token_value" not in caplog.text and "status=500" in caplog.text


# --- The gate -----------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_blackout_window_edges(events):
    events.append(_event(0))
    assert await ec.is_no_trade_zone("EURUSD", dt=NOW - timedelta(minutes=30), buffer_minutes=30)
    assert await ec.is_no_trade_zone("EURUSD", dt=NOW + timedelta(minutes=30), buffer_minutes=30)
    assert not await ec.is_no_trade_zone("EURUSD", dt=NOW + timedelta(minutes=30, seconds=1), buffer_minutes=30)
    assert not await ec.is_no_trade_zone("EURUSD", dt=NOW - timedelta(minutes=31), buffer_minutes=30)


@pytest.mark.asyncio
async def test_only_high_impact_usd_events_gate_usd_sensitive_symbols(events):
    events.extend([_event(0, currency="EUR"), _event(0, impact="medium")])
    assert not await ec.is_no_trade_zone("EURUSD", dt=NOW)
    events.append(_event(0, naive=True))  # a naive time from the DB cache is UTC
    for symbol in ("EURUSD", "EUR/USD", "eur-usd", "XAUUSD", "BTCUSDT", "US500"):
        assert await ec.is_no_trade_zone(symbol, dt=NOW), symbol
    for symbol in ("EURJPY", "GBP/JPY", "SOLUSDT"):
        assert not await ec.is_no_trade_zone(symbol, dt=NOW), symbol


def test_the_sync_gate_works_from_the_engines_executor_thread(events):
    events.append(_event(0, base=datetime.now(timezone.utc)))
    results: dict[str, bool] = {}

    def engine_thread():
        results["thread"] = ec.is_no_trade_zone_sync("EURUSD", buffer_minutes=60)

    worker = threading.Thread(target=engine_thread)
    worker.start()
    worker.join(30)
    results["main"] = ec.is_no_trade_zone_sync("EURUSD", buffer_minutes=60)

    async def inside_a_running_loop():
        return ec.is_no_trade_zone_sync("EURUSD", buffer_minutes=60)

    results["loop"] = asyncio.run(inside_a_running_loop())
    assert results == {"thread": True, "main": True, "loop": True}


def test_an_unavailable_gate_is_logged_once_not_silently(monkeypatch, caplog):
    async def broken(force_refresh: bool = False):
        raise ConnectionError("calendar down")

    monkeypatch.setattr(ec, "fetch_economic_events", broken)
    monkeypatch.setattr(ec, "_LAST_GATE_WARNING", 0.0)
    caplog.set_level("WARNING")
    assert ec.is_no_trade_zone_sync("EURUSD") is False  # existing policy: do not block
    assert ec.is_no_trade_zone_sync("GBPUSD") is False
    assert caplog.text.count("news gate unavailable") == 1


# --- Caching and fallback -----------------------------------------------------------------------

@pytest.fixture
def providers(monkeypatch):
    calls = {"ff": 0, "finnhub": 0, "stored": []}
    feed: list[dict] = []

    async def none():
        return []

    async def ff(from_dt, to_dt):
        calls["ff"] += 1
        return list(feed)

    async def finnhub(from_dt, to_dt):
        calls["finnhub"] += 1
        return []

    monkeypatch.setattr(ec, "_load_events_from_redis", none)
    monkeypatch.setattr(ec, "_load_events_from_db", none)
    monkeypatch.setattr(ec, "_fetch_forex_factory", ff)
    monkeypatch.setattr(ec, "_fetch_finnhub", finnhub)
    monkeypatch.setattr(ec, "_store_events_in_redis", lambda events: calls["stored"].append(events))
    monkeypatch.setattr(ec, "_EVENTS_CACHE", [])
    monkeypatch.setattr(ec, "_CACHE_FETCHED_AT", None)
    monkeypatch.setattr(ec, "_CACHE_IS_FALLBACK", False)
    return calls, feed


@pytest.mark.asyncio
async def test_a_failed_fetch_is_never_shared_and_is_retried_within_minutes(providers):
    calls, feed = providers
    events = await ec.fetch_economic_events()
    assert all(e["source"] == "fallback" and e["event_time"] is None for e in events)
    assert calls["stored"] == [] and ec.calendar_status()["fallback"] is True
    await ec.fetch_economic_events()
    assert calls["ff"] == 1  # still inside the short retry window
    ec._CACHE_FETCHED_AT -= timedelta(seconds=ec._FALLBACK_RETRY_SECONDS + 1)
    feed.append(_event(60, base=datetime.now(timezone.utc)))
    events = await ec.fetch_economic_events()
    assert calls["ff"] == 2 and events[0]["source"] == "test"
    assert len(calls["stored"]) == 1 and ec.calendar_status() | {"fetched_at": None} == {
        "fallback": False, "events": 1, "timed_events": 1, "sources": ["test"], "fetched_at": None}


@pytest.mark.asyncio
async def test_redis_cache_round_trip_keeps_utc_and_drops_old_fallback_entries(monkeypatch):
    from core.redis_state import state

    stored: dict[str, str] = {}
    monkeypatch.setattr(state, "set_sync", lambda key, value, ex=None: stored.__setitem__(key, value))
    monkeypatch.setattr(state, "get_sync", lambda key: stored.get(key))
    ec._store_events_in_redis([_event(15)])
    loaded = await ec._load_events_from_redis()
    assert loaded[0]["event_time"] == NOW + timedelta(minutes=15)
    stored[ec.REDIS_EVENTS_KEY] = json.dumps([{"title": "NFP", "currency": "USD", "impact": "high",
                                                 "event_time": None, "source": "fallback"}])
    assert await ec._load_events_from_redis() == []


@pytest.mark.asyncio
async def test_macro_context_reports_nearest_events_and_pressure(events, monkeypatch):
    monkeypatch.setattr(ec, "NO_TRADE_BUFFER_MINUTES", 30)
    events.extend([_event(-10, title="CPI"), _event(20, title="FOMC"), _event(-200, title="Old")])
    ctx = await ec.get_macro_news_context(now=NOW)
    assert ctx["minutes_since_high_impact_news"] == pytest.approx(10)
    assert ctx["minutes_until_high_impact_news"] == pytest.approx(20)
    assert (ctx["last_high_impact_news_title"], ctx["next_high_impact_news_title"]) == ("CPI", "FOMC")
    assert ctx["news_event_impact_score"] == pytest.approx(1 - 10 / 30)


# --- Database cache (real PostgreSQL) -----------------------------------------------------------

@pytest_asyncio.fixture
async def isolated_postgres():
    from db.session import dispose_engine_for_event_loop, get_session

    url = os.getenv("DATABASE_URL", "")
    if not url:
        if os.getenv("SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED") == "1":
            pytest.fail("real PostgreSQL integration required but DATABASE_URL is missing")
        pytest.skip("requires an isolated PostgreSQL test database")
    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql" and os.getenv("APP_ENV") == "test"
    assert parsed.host in {"127.0.0.1", "localhost"} and "test" in (parsed.database or "")
    async with get_session() as session:
        assert (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    yield
    await dispose_engine_for_event_loop()


@pytest.mark.asyncio
async def test_sync_worker_stores_events_and_the_db_cache_keeps_the_post_release_window(isolated_postgres, monkeypatch):
    from db.session import get_session
    from worker import news_sync_worker as worker

    tag = uuid4().hex[:8]
    now = datetime.now(timezone.utc).replace(microsecond=0)
    fetched = [
        {"title": f"just-released-{tag}", "currency": "USD", "impact": "high", "event_time": now - timedelta(minutes=30), "source": "forex_factory"},
        {"title": f"upcoming-{tag}", "currency": "USD", "impact": "high", "event_time": now + timedelta(hours=2), "source": "forex_factory"},
        {"title": f"fallback-{tag}", "currency": "USD", "impact": "high", "event_time": None, "source": "fallback"},
    ]

    async def fake_fetch(force_refresh: bool = False):
        return fetched

    monkeypatch.setattr(worker, "fetch_economic_events", fake_fetch)
    monkeypatch.setattr(worker, "ENABLE_NEWS_SYNC", True)
    async with get_session() as session:
        await session.execute(text("INSERT INTO economic_events(event_date,currency,title,impact,source,fetched_at) "
                                   "VALUES(:d,'USD',:t,'high','test',NOW())"),
                              {"d": (now - timedelta(days=3)).replace(tzinfo=None), "t": f"stale-{tag}"})
        await session.commit()
    try:
        result = await worker.sync_economic_events_to_db()
        assert result["status"] == "success" and result["synced"] == 2 and result["failed"] == 0, result
        async with get_session() as session:
            rows = dict((await session.execute(text(
                "SELECT title, event_date FROM economic_events WHERE title LIKE :p"), {"p": f"%{tag}"})).all())
        assert f"stale-{tag}" not in rows  # cleanup ran (naive cutoff)
        assert rows[f"just-released-{tag}"] == (now - timedelta(minutes=30)).replace(tzinfo=None)  # naive UTC
        cached = {e["title"]: e for e in await ec._load_events_from_db()}
        assert f"just-released-{tag}" in cached and f"upcoming-{tag}" in cached
    finally:
        async with get_session() as session:
            await session.execute(text("DELETE FROM economic_events WHERE title LIKE :p"), {"p": f"%{tag}"})
            await session.commit()
