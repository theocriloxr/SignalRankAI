"""SMC order-block setup and news-window tracking (owner request, 15 Nov 2026)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from strategies import structure_setups as ss


def _bar(o, c, wick=0.2):
    return {"open": o, "high": max(o, c) + wick, "low": min(o, c) - wick, "close": c}


def _bullish_bos_chart():
    bars = []
    price = 100.0
    for i in range(40):  # drift with small swings
        nxt = price + (0.3 if i % 6 < 3 else -0.3)
        bars.append(_bar(price, nxt))
        price = nxt
    # swing high around 101.x then pull back
    for step in (0.5, 0.5, 0.4, -0.6, -0.6, -0.6, -0.5):
        bars.append(_bar(price, price + step)); price += step
    # order block: last bearish candle before the impulse
    bars.append(_bar(price, price - 0.4)); price -= 0.4
    ob_low, ob_high = price - 0.2, price + 0.4 + 0.2
    # impulse up through the swing high
    for step in (1.2, 1.4, 1.3, 1.1):
        bars.append(_bar(price, price + step)); price += step
    # pull back toward the block without touching it, forming a minor low (inducement)
    for step in (-0.8, -0.9, 0.5, 0.4, -0.9, -1.0, -1.0, -0.5):
        bars.append(_bar(price, price + step, wick=0.1)); price += step
    # confirmation bar: wick into the block, close back above it
    close = price + 0.4
    bars.append({"open": price, "high": close + 0.1, "low": ob_high - 0.1, "close": close})
    bars.append(_bar(close, close + 0.1))  # forming bar
    return bars, ob_low, ob_high


def test_smc_order_block_follows_the_checklist():
    candles, ob_low, ob_high = _bullish_bos_chart()
    found = [x for x in ss.detect_setups(candles) if x["strategy_name"] == "SMC Order Block"]
    assert found, "expected a bullish order-block setup"
    setup = found[0]
    assert setup["direction"] == "LONG"
    assert setup["stop"] < setup["zone_low"] <= setup["zone_high"] < setup["entry"]
    risk = setup["entry"] - setup["stop"]
    assert setup["targets"][0] - setup["entry"] >= risk


def test_smc_needs_confirmation_close():
    candles, _lo, ob_high = _bullish_bos_chart()
    o = candles[-2]["open"]
    candles[-2] = {"open": o, "high": o + 0.1, "low": ob_high - 0.1, "close": ob_high - 0.05}
    assert not [x for x in ss.detect_setups(candles) if x["strategy_name"] == "SMC Order Block"]


def test_news_window_event_reports_title_and_side(monkeypatch):
    from services import economic_calendar as cal

    release = datetime(2026, 11, 13, 13, 30, tzinfo=timezone.utc)

    async def events(force_refresh=False):
        return [{"title": "PPI m/m", "currency": "USD", "impact": "high", "event_time": release}]

    monkeypatch.setattr(cal, "fetch_economic_events", events)
    before = asyncio.run(cal.news_window_event("XAUUSD", release - timedelta(minutes=20), 60))
    assert before["title"] == "PPI m/m" and before["minutes_from_event"] == -20.0
    assert asyncio.run(cal.news_window_event("NAS100", release + timedelta(minutes=5), 60))
    assert asyncio.run(cal.news_window_event("XAUUSD", release + timedelta(minutes=90), 60)) is None
    assert asyncio.run(cal.news_window_event("EURJPY", release, 60)) is None


def test_news_window_exemption_is_per_cell(monkeypatch):
    from core.gate_evidence import exempt

    monkeypatch.setenv("QUALITY_GATE_EVIDENCE_EXEMPTIONS", "news_window:commodity:15m")
    assert exempt("news_window", "commodity", "15m")
    assert not exempt("news_window", "fx", "15m")


def test_trade_check_outcome_reaches_email_even_with_alerts_off(monkeypatch):
    """A transactional event (the outcome of a user's own trade check) uses every connected channel."""
    import os

    import pytest
    from sqlalchemy import text

    dsn = os.getenv("SIGNALRANK_TEST_PG_DSN")
    if not dsn:
        pytest.skip("needs SIGNALRANK_TEST_PG_DSN")
    from sqlalchemy.ext.asyncio import create_async_engine

    from db.session import _normalize_database_url
    from services import notification_channels as nc

    url = _normalize_database_url(dsn, async_driver=True)
    monkeypatch.setenv("DATABASE_URL", url)

    async def scenario():
        from db.session import dispose_engine_for_event_loop

        engine = create_async_engine(url)
        uid = None
        try:
            async with engine.begin() as conn:
                uid = (await conn.execute(text(
                    "INSERT INTO users (created_at, tier, primary_email, email_verified_at) "
                    "VALUES (NOW(), 'free', 'idea.outcome@example.com', NOW()) RETURNING id"))).scalar_one()
                await conn.execute(text("INSERT INTO notification_preferences(user_id, email_enabled, push_enabled) "
                                        "VALUES (:u, FALSE, FALSE)"), {"u": uid})
                for nid, transactional in (("idea-evt-t", True), ("idea-evt-n", False)):
                    data = '{"kind":"trade_idea_outcome","transactional":true}' if transactional else '{"kind":"x"}'
                    await conn.execute(text(
                        "INSERT INTO notification_events(notification_id,user_id,event_type,title,body,severity,"
                        "channel_data,created_at) VALUES (:n,:u,'alert','Your XAUUSD idea reached TP1','body','info',"
                        "CAST(:d AS JSONB), NOW() AT TIME ZONE 'utc')"), {"n": nid, "u": uid, "d": data})
            await nc.dispatch_once()
            async with engine.connect() as conn:
                sent = {r[0]: r[1] for r in (await conn.execute(text(
                    "SELECT notification_id, channel FROM notification_channel_deliveries "
                    "WHERE notification_id IN ('idea-evt-t','idea-evt-n') AND channel='email'"))).all()}
            assert "idea-evt-t" in sent and "idea-evt-n" not in sent
        finally:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM email_outbox WHERE idempotency_key LIKE 'notify:idea-evt-%'"))
                await conn.execute(text("DELETE FROM notification_channel_deliveries WHERE notification_id LIKE 'idea-evt-%'"))
                await conn.execute(text("DELETE FROM notification_events WHERE notification_id LIKE 'idea-evt-%'"))
                if uid is not None:
                    await conn.execute(text("DELETE FROM notification_preferences WHERE user_id=:u"), {"u": uid})
                    await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": uid})
            await engine.dispose()
            await dispose_engine_for_event_loop()

    asyncio.run(scenario())


def test_news_window_follows_each_instruments_own_currencies(monkeypatch):
    from services import economic_calendar as ec

    monkeypatch.delenv("NEWS_WINDOW_ALL_CURRENCIES", raising=False)
    assert ec.event_currencies("EURGBP") == {"EUR", "GBP"}
    assert ec.event_currencies("AUDCAD") == {"AUD", "CAD"}
    assert ec.event_currencies("EURUSD") == {"EUR", "USD"}
    assert ec.event_currencies("GER40") == {"EUR"} and ec.event_currencies("JP225") == {"JPY"}
    assert "USD" in ec.event_currencies("US2000") and "USD" in ec.event_currencies("XAUUSD")
    monkeypatch.setenv("NEWS_WINDOW_ALL_CURRENCIES", "0")
    assert ec.event_currencies("EURGBP") == set() and ec.event_currencies("EURUSD") == {"USD"}
    assert ec._surprise({"actual": "0.4%", "forecast": "0.2%"}) == "above"
    assert ec._surprise({"actual": None, "forecast": "0.2%"}) is None
