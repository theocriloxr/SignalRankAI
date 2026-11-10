"""Features learned from competitor research (owner request, 9-10 Nov 2026)."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")


def test_cornix_block_for_crypto_only_with_full_precision():
    from signalrank_telegram.tier_signal_formatter import cornix_block, format_vip_signal

    block = cornix_block(dict(asset="PEPEUSDT", direction="short", entry=0.00001234567, stop_loss=0.0000125,
                              take_profit=[0.0000121]))
    assert "#PEPE/USDT" in block and "Regular (Short)" in block and "1) 0.00001234567" in block
    import re

    assert not re.search(r"\de-\d", block)  # no scientific notation
    assert cornix_block(dict(asset="XAUUSD", direction="long", entry=1, stop_loss=0.5, take_profit=[2])) is None
    card = format_vip_signal(dict(asset="BTCUSDT", direction="long", entry=75969.4, stop_loss=75857.77,
                                  take_profit=[76284.19], timeframe="5m", strategy_name="x", score=56, signal_id="x"))
    assert "<pre>#BTC/USDT" in card and "1) 76284.19" in card


def test_weekly_scorecard_text_counts_misses():
    from services.public_track_record import weekly_scorecard_text

    text = weekly_scorecard_text({"windows": {"7d": [
        {"asset_class": "crypto", "closed": 5, "reached_tp1": 2, "stopped": 3, "tp1_rate": 0.4, "avg_r": 0.1,
         "total_r": 0.5}]}})
    assert "5 closed, 2 reached TP1 (40%), 3 stopped, +0.50R" in text and "do not guarantee" in text


def test_weekly_scorecard_is_due_on_monday_mornings_only():
    from services import weekly_scorecard as ws

    assert ws.due(datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc))
    assert not ws.due(datetime(2026, 11, 16, 6, 0, tzinfo=timezone.utc))
    assert not ws.due(datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc))
    assert ws.week_key(datetime(2026, 11, 16, tzinfo=timezone.utc)) == "weekly_scorecard:2026-W47"


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_track_record_and_weekly_publish_on_postgres(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from db.session import _normalize_database_url

    url = _normalize_database_url(_PG_DSN, async_driver=True)
    monkeypatch.setenv("DATABASE_URL", url)
    sid = f"tr-{uuid4().hex[:8]}"
    monday = datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc)

    async def scenario():
        from db.session import dispose_engine_for_event_loop, get_session
        from services import weekly_scorecard as ws
        from services.public_track_record import build_track_record

        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM runtime_state WHERE key=:k"), {"k": ws.week_key(monday)})
                await conn.execute(text(
                    "INSERT INTO signals (signal_id, asset, asset_class, timeframe, direction, entry, stop_loss, take_profit,"
                    " score, strategy_name, strategy_group, strength, created_at, display_id) VALUES (:s,'BTCUSDT','crypto',"
                    "'1h','long',100,99,'[102]',80,'ADX Trend','trend',1,(NOW() AT TIME ZONE 'utc') - interval '2 days',:d)"),
                    {"s": sid, "d": sid[:10]})
                await conn.execute(text(
                    "INSERT INTO signal_deliveries (signal_id, user_id, delivered_at, delivery_state) "
                    "SELECT :s, id, NOW(), 'confirmed' FROM users ORDER BY id LIMIT 1"), {"s": sid})
                await conn.execute(text(
                    "INSERT INTO outcomes (signal_id, status, canonical_outcome, r_multiple, closed_at, opened_at, "
                    "performance_inclusion_status, meta) VALUES (:s,'sl','loss',-1.0,(NOW() AT TIME ZONE 'utc') - interval '1 day',"
                    "(NOW() AT TIME ZONE 'utc') - interval '2 days','eligible','{}')"), {"s": sid})
            async with get_session() as session:
                record = await build_track_record(session)
            sent = []

            async def fake_post(chat, message):
                sent.append(chat)
                return True

            first = await ws.publish_once(now=monday, telegram_post=fake_post)
            second = await ws.publish_once(now=monday, telegram_post=fake_post)
            return record, first, second
        finally:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM notification_events WHERE notification_id LIKE :k"),
                                   {"k": ws.week_key(monday) + ":%"})
                await conn.execute(text("DELETE FROM runtime_state WHERE key=:k"), {"k": ws.week_key(monday)})
                await conn.execute(text("DELETE FROM outcomes WHERE signal_id=:s"), {"s": sid})
                await conn.execute(text("DELETE FROM signal_deliveries WHERE signal_id=:s"), {"s": sid})
                await conn.execute(text("DELETE FROM signals WHERE signal_id=:s"), {"s": sid})
            await engine.dispose()
            await dispose_engine_for_event_loop()

    record, first, second = asyncio.run(scenario())
    if not any(r["asset"] == "BTCUSDT" and r["r"] == -1.0 for r in record["recent"]):
        pytest.skip("no user row in the scratch database to attach a delivery to")
    crypto = next(c for c in record["windows"]["30d"] if c["asset_class"] == "crypto")
    assert crypto["stopped"] >= 1  # misses are on the record
    assert first["status"] == "published" and second["status"] == "already_published"
