"""Setup records page (owner request, 8 Nov 2026): each setup's record and the smallest TP1 R/R it supports."""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")


def test_card_is_on_the_performance_page():
    view = (ROOT / "frontend" / "src" / "components" / "WorkspaceLive.tsx").read_text(encoding="utf-8")
    assert "<SetupRecords/>" in view
    assert '"/api/v1/platform/setup-records"' in (ROOT / "frontend" / "src" / "lib" / "api.d.ts").read_text("utf-8")


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_setup_records_on_postgres(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from db.session import _normalize_database_url
    from services import segment_evidence

    url = _normalize_database_url(_PG_DSN, async_driver=True)
    monkeypatch.setenv("DATABASE_URL", url)
    snapshot = {"computed_at": time.time(), "lookback_days": 60, "segments": {
        "adx trend|5m|long": {"n": 3235, "wins": 1205},
        "zone flip retest|15m|short": {"n": 0, "wins": 0},
        "channel break|15m|long": {"n": 40, "wins": 30},
    }}

    async def scenario():
        from db.session import dispose_engine_for_event_loop
        from web import platform_api as api

        engine = create_async_engine(url)
        async with engine.begin() as conn:
            before = (await conn.execute(text("SELECT value FROM runtime_state WHERE key=:k"),
                                         {"k": segment_evidence.SNAPSHOT_KEY})).scalar_one_or_none()
            await conn.execute(text(
                "INSERT INTO runtime_state(key, value, expires_at, updated_at) VALUES (:k, CAST(:v AS JSONB), NULL, NOW()) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"), {"k": segment_evidence.SNAPSHOT_KEY,
                                                                           "v": json.dumps(snapshot)})
        try:
            out = await api.setup_records(user={"id": 1, "tier": "free"})
            rows = {(r["strategy"], r["timeframe"], r["direction"]): r for r in out["setups"]}
            assert out["current"] is True
            adx = rows[("adx trend", "5m", "long")]
            # 1205/3235 = 37 %; lower bound ~35.6 % -> TP1 must pay >= (1/0.356 - 1) / 0.5 ~ 3.6R
            assert 3.4 < adx["min_tp1_rr"] < 3.8 and adx["deck_strategy"] is False
            assert rows[("zone flip retest", "15m", "short")]["min_tp1_rr"] is None
            assert rows[("channel break", "15m", "long")]["deck_strategy"] is True
            assert out["setups"][0]["deck_strategy"] is True  # deck setups listed first
        finally:
            async with engine.begin() as conn:
                if before is None:
                    await conn.execute(text("DELETE FROM runtime_state WHERE key=:k"), {"k": segment_evidence.SNAPSHOT_KEY})
                else:
                    await conn.execute(text("UPDATE runtime_state SET value=CAST(:v AS JSONB) WHERE key=:k"),
                                       {"k": segment_evidence.SNAPSHOT_KEY, "v": json.dumps(before)})
            await engine.dispose()
            await dispose_engine_for_event_loop()

    asyncio.run(scenario())
