"""Engine Pulse reports the window it names (8 Nov 2026).

Owner report: the hourly pulse on 4, 5 and 6 Nov showed "Window: trailing 1h"
with "ml: 736224", "score: 112188" (identical every day), "Decision rows
evaluated: 5" and "Unaccounted: 5". ``compute_engine_health`` passed a
timezone-aware ``since`` to ``timestamp without time zone`` columns; asyncpg
refuses that, so every window query failed (logged at debug) and the pulse fell
back to the engine's lifetime counters and the latest cycle's asset count.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")


def test_window_bound_is_naive_utc_and_failures_are_visible():
    source = (ROOT / "engine" / "admin_pulse.py").read_text(encoding="utf-8")
    assert "timedelta(hours=max(1, int(window_hours or 1)))).replace(tzinfo=None)" in source
    assert 'logger.warning("[admin_pulse] decision_log window query failed' in source
    assert "WHERE id >= :min_id AND created_at >= :since" in source
    assert "False Negatives (would have hit TP3)" not in source


def test_lifetime_counters_are_labelled():
    from engine.admin_pulse import _source_note

    assert _source_note("window") == ""
    assert "lifetime totals" in _source_note("lifetime_counters")
    assert "latest engine cycle" in _source_note("latest_cycle")


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_pulse_counts_only_the_window_on_postgres(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from db.session import _normalize_database_url

    monkeypatch.setenv("DATABASE_URL", _normalize_database_url(_PG_DSN, async_driver=True))

    async def scenario():
        engine = create_async_engine(_normalize_database_url(_PG_DSN, async_driver=True))
        try:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM decision_log WHERE asset LIKE 'PULSET%'"))
                await conn.execute(text(
                    "INSERT INTO decision_log (asset, timeframe, decision, reason, meta, created_at) "
                    "SELECT 'PULSET' || g, '5m', 'rejected', CASE WHEN g % 2 = 0 THEN 'ml_filter' "
                    "ELSE 'regime: choppy' END, json_build_object('layer', 'ml', 'actual_outcome', "
                    "CASE WHEN g % 3 = 0 THEN 'tp1' ELSE 'sl' END, 'outcome_tracked_at', '2026-11-08T00:00:00'), "
                    "(NOW() AT TIME ZONE 'utc') - (g || ' minutes')::interval FROM generate_series(1, 40) g"))
                await conn.execute(text(
                    "INSERT INTO decision_log (asset, timeframe, decision, reason, meta, created_at) "
                    "VALUES ('PULSETOLD', '5m', 'rejected', 'ml_filter', '{}', "
                    "(NOW() AT TIME ZONE 'utc') - interval '5 hours')"))
            from db import session as db_session

            if hasattr(db_session, "_reset_engines_for_tests"):
                db_session._reset_engines_for_tests()
            from engine.admin_pulse import compute_engine_health

            stats = await compute_engine_health(window_hours=1)
            assert stats["db_window_failed"] is False
            assert stats["rejected_source"] == "window"
            assert stats["rejected_by"].get("ml", 0) >= 20 and stats["rejected_by"].get("regime", 0) >= 20
            assert stats["scanned"] >= 40 and stats["unaccounted"] == 0
            assert stats["shadow"]["source"] == "window"
            assert stats["shadow"]["false_negative"] >= 13 and stats["shadow"]["correct_block"] >= 27
        finally:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM decision_log WHERE asset LIKE 'PULSET%'"))
            await engine.dispose()

    asyncio.run(scenario())
