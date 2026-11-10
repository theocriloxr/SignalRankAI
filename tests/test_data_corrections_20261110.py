"""Audited data corrections (owner: correct all wrong database details, 10 Nov 2026)."""
from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest

_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_each_audited_correction_touches_only_its_pattern(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from db.session import _normalize_database_url

    url = _normalize_database_url(_PG_DSN, async_driver=True)
    monkeypatch.setenv("DATABASE_URL", url)
    tag = uuid4().hex[:6]
    sid = {k: f"dc{tag}-{k}" for k in ("broken", "broken_sent", "bigwin", "realwin", "pending_old", "pending_new",
                                        "life_old", "life_sent")}

    async def scenario():
        from db.session import dispose_engine_for_event_loop
        from services import data_corrections as dc

        engine = create_async_engine(url)

        async def sig(conn, key, entry, stop, age_days, status="shadow_rejected"):
            await conn.execute(text(
                "INSERT INTO signals (signal_id, asset, timeframe, direction, entry, stop_loss, take_profit, score,"
                " strategy_name, strategy_group, strength, status, created_at, display_id) VALUES (:s,'BTCUSDT','1m','long',"
                ":e,:sl,'[1]',70,'x','trend',1,:st,(NOW() AT TIME ZONE 'utc') - make_interval(days => :d),:disp)"),
                {"s": sid[key], "e": entry, "sl": stop, "st": status, "d": age_days, "disp": sid[key][-12:]})

        try:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM runtime_state WHERE key=:k"), {"k": dc.MARKER})
                uid = (await conn.execute(text("SELECT id FROM users ORDER BY id LIMIT 1"))).scalar()
                await sig(conn, "broken", 100, 100, 40)
                await sig(conn, "broken_sent", 100, 100, 40, "active")
                await sig(conn, "bigwin", 561.94, 561.892, 100)
                await sig(conn, "realwin", 100, 99, 100)
                await sig(conn, "pending_old", 100, 99, 60)
                await sig(conn, "pending_new", 100, 99, 5)
                await sig(conn, "life_old", 100, 99, 60)
                await sig(conn, "life_sent", 100, 99, 60)
                if uid is not None:
                    await conn.execute(text("INSERT INTO signal_deliveries(signal_id,user_id,delivered_at,sent_ok,delivery_state)"
                                            " VALUES (:s,:u,NOW(),TRUE,'confirmed')"), {"s": sid["broken_sent"], "u": uid})
                    await conn.execute(text("INSERT INTO signal_deliveries(signal_id,user_id,delivered_at,sent_ok,delivery_state)"
                                            " VALUES (:s,:u,NOW(),TRUE,'confirmed')"), {"s": sid["life_sent"], "u": uid})
                for key, r in (("bigwin", 63.7), ("realwin", 3.0)):
                    await conn.execute(text("INSERT INTO outcomes(signal_id,status,canonical_outcome,r_multiple,closed_at,opened_at,"
                                            "performance_inclusion_status,meta) VALUES (:s,'tp3','win',:r,NOW(),NOW(),'eligible','{}')"),
                                       {"s": sid[key], "r": r})
                for key in ("pending_old", "pending_new"):
                    await conn.execute(text("INSERT INTO outcomes(signal_id,status,canonical_outcome,r_multiple,opened_at,meta)"
                                            " VALUES (:s,'pending','pending',0,NULL,'{}')"), {"s": sid[key]})
                for key in ("life_old", "life_sent"):
                    await conn.execute(text("INSERT INTO signal_lifecycles(signal_id,state,watch_started_at) VALUES (:s,'ACTIVE_TRADE',NOW())"),
                                       {"s": sid[key]})
            first = await dc.run_once()
            second = await dc.run_once()
            async with engine.begin() as conn:
                status = dict((await conn.execute(text("SELECT signal_id, status FROM signals WHERE signal_id = ANY(:i)"),
                                                  {"i": list(sid.values())})).all())
                incl = dict((await conn.execute(text("SELECT signal_id, performance_inclusion_status FROM outcomes WHERE signal_id = ANY(:i)"),
                                                {"i": list(sid.values())})).all())
                ostat = dict((await conn.execute(text("SELECT signal_id, status FROM outcomes WHERE signal_id = ANY(:i)"),
                                                 {"i": list(sid.values())})).all())
                life = dict((await conn.execute(text("SELECT signal_id, state FROM signal_lifecycles WHERE signal_id = ANY(:i)"),
                                                {"i": list(sid.values())})).all())
            return uid, first, second, status, incl, ostat, life
        finally:
            async with engine.begin() as conn:
                for table in ("signal_lifecycles", "outcomes", "signal_deliveries"):
                    await conn.execute(text(f"DELETE FROM {table} WHERE signal_id = ANY(:i)"), {"i": list(sid.values())})
                await conn.execute(text("DELETE FROM signals WHERE signal_id = ANY(:i)"), {"i": list(sid.values())})
                await conn.execute(text("DELETE FROM runtime_state WHERE key=:k"), {"k": "maintenance:data_corrections:20261110:done"})
            await engine.dispose()
            await dispose_engine_for_event_loop()

    uid, first, second, status, incl, ostat, life = asyncio.run(scenario())
    assert first["status"] == "done" and second["status"] == "already_done"
    assert status[sid["broken"]] == "invalid_geometry"
    assert incl[sid["bigwin"]] == "excluded" and incl[sid["realwin"]] == "eligible"
    assert ostat[sid["pending_old"]] == "expired" and ostat[sid["pending_new"]] == "pending"
    assert life[sid["life_old"]] == "EXPIRED"
    if uid is not None:  # delivered rows are never rewritten
        assert status[sid["broken_sent"]] == "active" and life[sid["life_sent"]] == "ACTIVE_TRADE"
