"""Live candle flow on the signal page and a paper desk that separates open and closed trades (8 Nov 2026)."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")


def test_paper_desk_splits_open_and_closed_and_returns_exit_price():
    api = (ROOT / "web" / "platform_api.py").read_text(encoding="utf-8")
    view = (ROOT / "frontend" / "src" / "components" / "WorkspaceLive.tsx").read_text(encoding="utf-8")
    assert "e.entry_type='POSITION_CLOSED'" in api and "AS exit_price" in api
    assert '<Card title="Open positions">' in view and '<Card title="Closed trades">' in view
    assert "Equity = starting balance" in view


def test_chart_polls_the_live_endpoint():
    chart = (ROOT / "frontend" / "src" / "components" / "SignalChart.tsx").read_text(encoding="utf-8")
    assert '"/api/v1/platform/signals/{signal_id}/candles"' in chart
    assert 'document.visibilityState === "hidden"' in chart and "export function mergeCandles" in chart
    types = (ROOT / "frontend" / "src" / "lib" / "api.d.ts").read_text(encoding="utf-8")
    assert '"/api/v1/platform/signals/{signal_id}/candles"' in types


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_live_candles_endpoint_on_postgres(monkeypatch):
    from fastapi import HTTPException
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from db.session import _normalize_database_url

    monkeypatch.setenv("DATABASE_URL", _normalize_database_url(_PG_DSN, async_driver=True))

    async def scenario():
        engine = create_async_engine(_normalize_database_url(_PG_DSN, async_driver=True))
        uid = None
        try:
            async with engine.begin() as conn:
                uid = (await conn.execute(text("INSERT INTO users (created_at) VALUES (NOW()) RETURNING id"))).scalar_one()
                await conn.execute(text(
                    "INSERT INTO signals (signal_id, asset, timeframe, direction, entry, stop_loss, take_profit, score, "
                    "strategy_name, strategy_group, strength, created_at, display_id) VALUES ('livet-1','LIVETUSDT','5m',"
                    "'long',100,99,'[103]',80,'ADX Trend','trend',1,(NOW() AT TIME ZONE 'utc') - interval '30 minutes','livet1')"))
                await conn.execute(text("INSERT INTO signal_deliveries (user_id, signal_id, delivered_at, sent_ok) "
                                        "VALUES (:u,'livet-1',NOW() AT TIME ZONE 'utc',true)"), {"u": uid})
                await conn.execute(text("INSERT INTO signal_lifecycles (signal_id, state, last_price, last_checked_at) "
                                        "VALUES ('livet-1','TP1_HIT',101.7,NOW() AT TIME ZONE 'utc')"))
                await conn.execute(text(
                    "INSERT INTO market_candles (symbol,timeframe,open_time_ms,open,high,low,close,volume,is_final,updated_at) "
                    "SELECT 'LIVETUSDT','5m',(extract(epoch FROM NOW())*1000)::bigint/300000*300000 - g*300000,"
                    "100,101,99.5,100.5,0,g>0,NOW() FROM generate_series(0,9) g"))
            from web import platform_api as api

            first = await api.signal_live_candles("livet-1", after_ms=0, user={"id": uid})
            assert len(first["candles"]) == 10 and first["last_price"] == 101.7
            assert first["trade_status"]["code"] == "open_tp1" and first["closed"] is False
            newer = await api.signal_live_candles("livet-1", after_ms=first["candles"][-2]["t"], user={"id": uid})
            assert len(newer["candles"]) == 3  # re-sends the bar before, so a forming bar is refreshed
            with pytest.raises(HTTPException) as refused:
                await api.signal_live_candles("livet-1", after_ms=0, user={"id": uid + 10_000})
            assert refused.value.status_code == 404
        finally:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM market_candles WHERE symbol='LIVETUSDT'"))
                await conn.execute(text("DELETE FROM signal_lifecycles WHERE signal_id='livet-1'"))
                await conn.execute(text("DELETE FROM signal_deliveries WHERE signal_id='livet-1'"))
                await conn.execute(text("DELETE FROM signals WHERE signal_id='livet-1'"))
                if uid is not None:
                    await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": uid})
            await engine.dispose()

    asyncio.run(scenario())


def test_paper_desk_refuses_pegged_tokens():
    """Owner screenshot, 8 Nov 2026: an XAUTUSDT (tokenised gold) paper short. Pegged tokens are excluded
    from scanning since 1 Nov; the paper desk now also refuses them, quietly, as a recorded skip."""
    from core.paper_trading_service import _is_pegged_paper_asset

    assert _is_pegged_paper_asset("XAUTUSDT") and _is_pegged_paper_asset("PAXGUSDT")
    assert not any(_is_pegged_paper_asset(a) for a in ("BTCUSDT", "PEPEUSDT", "XAUUSD", "USDJPY"))
    source = (ROOT / "core" / "paper_trading_service.py").read_text(encoding="utf-8")
    assert 'reason="pegged_asset_excluded"' in source
