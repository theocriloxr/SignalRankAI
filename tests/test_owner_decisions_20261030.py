"""Owner decision of 30 Oct 2026 (docs/release/requirements_conflicts.md): when no
calendar source has event times, the high-impact news blackout does not block
signals (fail-open). With event times it blocks. Changing either needs a new
recorded owner decision."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services import economic_calendar as ec

NOW = datetime(2026, 11, 6, 13, 30, tzinfo=timezone.utc)  # an NFP release time


@pytest.mark.asyncio
async def test_no_calendar_source_does_not_block(monkeypatch):
    async def fallback_only(force_refresh: bool = False):
        return [{**event, "event_time": None, "source": "fallback"} for event in ec._FALLBACK_EVENTS]

    monkeypatch.setattr(ec, "fetch_economic_events", fallback_only)
    for symbol in ("EURUSD", "XAUUSD", "BTCUSDT", "US500"):
        assert await ec.is_no_trade_zone(symbol, dt=NOW, buffer_minutes=60) is False


def test_an_unreachable_calendar_does_not_block(monkeypatch):
    async def unreachable(force_refresh: bool = False):
        raise TimeoutError("calendar feeds unreachable")

    monkeypatch.setattr(ec, "fetch_economic_events", unreachable)
    assert ec.is_no_trade_zone_sync("EURUSD", buffer_minutes=60) is False


@pytest.mark.asyncio
async def test_with_event_times_the_blackout_still_blocks(monkeypatch):
    async def timed(force_refresh: bool = False):
        return [{"title": "Non-Farm Payrolls", "currency": "USD", "impact": "high",
                 "event_time": NOW, "source": "forex_factory"}]

    monkeypatch.setattr(ec, "fetch_economic_events", timed)
    assert await ec.is_no_trade_zone("EURUSD", dt=NOW - timedelta(minutes=59), buffer_minutes=60) is True
    assert await ec.is_no_trade_zone("EURUSD", dt=NOW + timedelta(minutes=61), buffer_minutes=60) is False


def test_the_engine_gate_uses_a_60_minute_window():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "engine" / "core.py").read_text(encoding="utf-8")
    assert "_is_no_trade_zone_sync(asset, buffer_minutes=60)" in source
