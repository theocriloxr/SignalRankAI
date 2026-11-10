"""Correct the stored asset class on past training rows (owner, 10 Nov 2026), then request a retrain."""
from __future__ import annotations

import asyncio
import json
import os
from datetime import timedelta

import pytest

_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_backfill_corrects_missing_and_wrong_classes_and_resumes(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from db.session import _normalize_database_url
    from utils.timeutils import now_utc_naive

    url = _normalize_database_url(_PG_DSN, async_driver=True)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("ASSET_CLASS_BACKFILL_WINDOW", "200")
    requested = []

    async def scenario():
        from core.redis_state import state
        from db.session import dispose_engine_for_event_loop
        from services import asset_class_backfill as bf

        monkeypatch.setattr(state, "set_sync", lambda key, value, ex=None: requested.append((key, value)))
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM runtime_state WHERE key IN (:a,:b)"),
                                   {"a": bf.DONE_KEY, "b": bf.CURSOR_KEY})
                await conn.execute(text("DELETE FROM decision_log WHERE reason='acbf'"))
                for i, (asset, features) in enumerate([("EURUSD", {}), ("XAUUSD", {"asset_class_enc": 0}),
                                                       ("BTCUSDT", {"asset_class_enc": 0}), ("AAPL", None)] * 3):
                    meta = {"layer": "ml", "outcome_tracked_at": "2026-11-09T00:00:00", "actual_outcome": "tp1"}
                    if features is not None:
                        meta["features"] = features
                    await conn.execute(text(
                        "INSERT INTO decision_log(asset,timeframe,decision,reason,meta,created_at) VALUES "
                        "(:a,'1h','rejected','acbf',CAST(:m AS JSONB),:t)"),
                        {"a": asset, "m": json.dumps(meta), "t": now_utc_naive() - timedelta(hours=2)})
            first = await bf.run(pause_seconds=0)
            second = await bf.run(pause_seconds=0)
            async with engine.begin() as conn:
                rows = (await conn.execute(text(
                    "SELECT asset, meta->'features'->>'asset_class_enc' FROM decision_log WHERE reason='acbf'"))).all()
            return first, second, rows
        finally:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM decision_log WHERE reason='acbf'"))
                await conn.execute(text("DELETE FROM runtime_state WHERE key LIKE 'maintenance:asset_class_backfill:%'"))
            await engine.dispose()
            await dispose_engine_for_event_loop()

    first, second, rows = asyncio.run(scenario())
    assert first["status"] == "done" and first["corrected"] >= 9  # BTCUSDT was already right
    assert second["status"] == "already_done"
    got = {(a, float(e)) for a, e in rows}
    assert got == {("EURUSD", 1.0), ("XAUUSD", 2.0), ("BTCUSDT", 0.0), ("AAPL", 3.0)}
    assert any(value == "asset_class_backfill" for _key, value in requested)  # retrain requested
