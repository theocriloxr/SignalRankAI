"""Actual SQL eligibility on a newly migrated, owned localhost database.

All readiness records below are synthetic fixtures, not provider certificates.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from core.focused_universe import select_focused_scan_assets
from data.database_universe import load_database_universe
from tests.test_adaptive_worker_research_postgres import worker_database  # noqa: F401


@pytest.mark.asyncio
async def test_focused_sql_rejects_incomplete_stale_future_and_misclassified_records(worker_database):
    now = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
    stamp = now.replace(tzinfo=None)
    async with worker_database() as session:
        await session.execute(text("""
            INSERT INTO instruments(instrument_id,canonical_symbol,display_symbol,asset_class,
                instrument_type,active,tradable,discovery_status,last_verified_at)
            VALUES ('focus-test','BTCUSDT','BTCUSDT','crypto','spot',TRUE,TRUE,'analysis_ready',:stamp)
        """), {"stamp": stamp})
        await session.execute(text("""
            INSERT INTO provider_instruments(provider,venue,provider_symbol,canonical_instrument_id,
                market_status,data_enabled,historical_candles_supported,live_quotes_supported,last_successful_refresh_at)
            VALUES ('synthetic-test','synthetic-test','BTCUSDT','focus-test','active',TRUE,TRUE,TRUE,:stamp)
        """), {"stamp": stamp})
        # A provider catalogue row alone cannot enter the focused scanner.
        assert await load_database_universe(session, require_analysis_ready=True, now=now) == []
        assert await load_database_universe(session) == ["BTCUSDT"]
        await session.execute(text("""
            INSERT INTO instrument_certifications(instrument_id,readiness_state,evidence,certified_at)
            VALUES ('focus-test','analysis_ready',CAST(:evidence AS JSONB),:stamp)
        """), {"stamp": stamp, "evidence": '{"synthetic_fixture": true}'})
        assert await load_database_universe(session, require_analysis_ready=True, now=now) == ["BTCUSDT"]

        mutations = [
            ("instruments", "active=FALSE"), ("instruments", "tradable=FALSE"),
            ("instruments", "discovery_status='metadata_validated'"),
            ("instruments", "asset_class='equity'"),
            ("instruments", "last_verified_at=NULL"),
            ("instruments", "last_verified_at=:stale"),
            ("instruments", "last_verified_at=:future"),
            ("provider_instruments", "data_enabled=FALSE"),
            ("provider_instruments", "market_status='suspended'"),
            ("provider_instruments", "historical_candles_supported=FALSE"),
            ("provider_instruments", "live_quotes_supported=FALSE"),
            ("provider_instruments", "last_successful_refresh_at=NULL"),
            ("provider_instruments", "last_successful_refresh_at=:stale"),
            ("provider_instruments", "last_successful_refresh_at=:future"),
            ("provider_instruments", "provider=''"),
            ("provider_instruments", "provider_symbol=''"),
            ("provider_instruments", "delisted_at=:stamp"),
            ("instrument_certifications", "readiness_state='metadata_validated'"),
            ("instrument_certifications", "evidence=NULL"),
            ("instrument_certifications", "certified_at=:stale"),
            ("instrument_certifications", "certified_at=:future"),
        ]
        params = {"stamp": stamp, "stale": stamp - timedelta(minutes=15, microseconds=1),
                  "future": stamp + timedelta(microseconds=1)}
        for table, mutation in mutations:
            transaction = await session.begin_nested()
            try:
                await session.execute(text(f"UPDATE {table} SET {mutation}"), params)
                symbols = await load_database_universe(session, require_analysis_ready=True, now=now)
                selected = select_focused_scan_assets(symbols, universe_source="database_registry",
                    environment={"FOCUSED_UNIVERSE_ENABLED": "1", "APP_ENV": "test"})
                assert selected.assets == (), (table, mutation)
                assert (await session.execute(text("SELECT COUNT(*) FROM instruments"))).scalar_one() == 1
            finally:
                await transaction.rollback()
        # Exact boundary is inclusive; a later scan expires the same records.
        assert await load_database_universe(session, require_analysis_ready=True, now=now + timedelta(minutes=15)) == ["BTCUSDT"]
        assert await load_database_universe(session, require_analysis_ready=True, now=now + timedelta(minutes=15, microseconds=1)) == []

        # A second incomplete provider cannot supply capabilities to the first.
        await session.execute(text("UPDATE provider_instruments SET live_quotes_supported=FALSE"))
        await session.execute(text("""
            INSERT INTO provider_instruments(provider,venue,provider_symbol,canonical_instrument_id,
                market_status,data_enabled,historical_candles_supported,live_quotes_supported,last_successful_refresh_at)
            VALUES ('synthetic-other','synthetic-test','BTCUSDT','focus-test','active',TRUE,FALSE,TRUE,:stamp)
        """), {"stamp": stamp})
        assert await load_database_universe(session, require_analysis_ready=True, now=now) == []
        await session.execute(text("UPDATE provider_instruments SET historical_candles_supported=TRUE, live_quotes_supported=TRUE"))
        assert await load_database_universe(session, require_analysis_ready=True, now=now, page_size=1) == ["BTCUSDT"]


@pytest.mark.asyncio
async def test_readiness_policy_rejects_ambiguous_clock_and_truthy_flags():
    with pytest.raises(ValueError, match="requires_timezone"):
        await load_database_universe(None, require_analysis_ready=True, now=datetime(2026, 10, 16))
    with pytest.raises(ValueError, match="must_be_boolean"):
        await load_database_universe(None, require_analysis_ready="false")
