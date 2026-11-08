"""Delivery latency breakdown (owner finding, 8 Nov 2026: entries arrive late)."""
from __future__ import annotations

import asyncio
import os

import pytest

from services.delivery_latency import format_latency_lines

_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")


def test_format_handles_empty_and_groups():
    assert "No confirmed deliveries" in format_latency_lines({"window_hours": 24, "groups": []})[0]
    lines = format_latency_lines({"window_hours": 24, "deliveries": 3, "groups": [{
        "asset_class": "crypto", "timeframe": "5m", "deliveries": 3, "engine_p50_s": 20.0, "engine_p90_s": 40.0,
        "queue_p50_s": 30.0, "queue_p90_s": 200.0, "send_p50_s": 1.0, "send_p90_s": 2.0,
        "total_p50_s": 31.0, "total_p90_s": 202.0, "late_share": 0.333}]})
    assert "crypto 5m ×3: 20s/40s | 30s/3.3m | 1s/2s | 33%" in lines[-1]


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_report_on_postgres():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from db.session import _normalize_database_url
    from services.delivery_latency import delivery_latency_report

    async def scenario():
        engine = create_async_engine(_normalize_database_url(_PG_DSN, async_driver=True))
        uid = None
        try:
            async with engine.begin() as conn:
                uid = (await conn.execute(text("INSERT INTO users (created_at) VALUES (NOW()) RETURNING id"))).scalar_one()
                # created 2 min into a 5m bar; send starts 60 s later; confirmed 1 s after.
                await conn.execute(text(
                    "INSERT INTO signals (signal_id, asset, asset_class, timeframe, direction, entry, stop_loss, take_profit, "
                    "score, strategy_name, strategy_group, strength, created_at, display_id) VALUES "
                    "('lat-1','LATUSDT','crypto','5m','long',1,0.9,'[1.2]',70,'x','x',1,"
                    "date_trunc('hour', NOW() AT TIME ZONE 'utc') + interval '2 minutes','lat1')"))
                await conn.execute(text(
                    "INSERT INTO signal_deliveries (user_id, signal_id, delivered_at, sent_ok, telegram_send_started_at, "
                    "delivery_confirmed_at) VALUES (:u,'lat-1',NOW(),true,"
                    "date_trunc('hour', NOW() AT TIME ZONE 'utc') + interval '3 minutes',"
                    "date_trunc('hour', NOW() AT TIME ZONE 'utc') + interval '3 minutes 1 second')"), {"u": uid})
            async with AsyncSession(engine) as session:
                report = await delivery_latency_report(session, hours=48)
            group = next(g for g in report["groups"] if g["asset_class"] == "crypto" and g["timeframe"] == "5m")
            assert group["engine_p50_s"] == 120.0 and group["queue_p50_s"] == 60.0 and group["send_p50_s"] == 1.0
            assert group["late_share"] == 1.0  # 3 min after the bar opened > a quarter of 5 min
        finally:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM signal_deliveries WHERE signal_id='lat-1'"))
                await conn.execute(text("DELETE FROM signals WHERE signal_id='lat-1'"))
                if uid is not None:
                    await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": uid})
            await engine.dispose()

    asyncio.run(scenario())
