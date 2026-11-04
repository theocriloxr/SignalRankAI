"""A stale market_ticks row is never used as a live price (4 Nov 2026).

Production: market_ticks was last written in July (EURGBP 0.85679 on 2 Jul, WTI
4.37, XAUUSD 4188.5). `_get_live_price_async` returned those prices for every
symbol Binance does not list, so the shadow tracker labelled EURGBP 15m long
setups (entry 0.83472, stop 0.83388, target 0.83714) `tp1` five minutes after the
rejection while the market traded 0.8344-0.8349, and every short `sl`.
"""
from __future__ import annotations

import asyncio
import contextlib
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

from engine import stale_signal_validator as ssv

NOW = datetime(2026, 11, 4, 6, 20, tzinfo=timezone.utc)


def test_fresh_tick_is_used():
    ms = (NOW - timedelta(seconds=30)).timestamp() * 1000
    assert ssv.fresh_tick_price(0.8347, ms, None, now=NOW) == pytest.approx(0.8347)


def test_july_tick_is_rejected():
    july_ms = datetime(2026, 7, 2, 17, 57, tzinfo=timezone.utc).timestamp() * 1000
    assert ssv.fresh_tick_price(0.85679, july_ms, datetime(2026, 7, 2, 17, 57, 9), now=NOW) is None


def test_updated_at_is_the_fallback_clock(monkeypatch):
    assert ssv.fresh_tick_price(1.1, None, (NOW - timedelta(seconds=60)).replace(tzinfo=None), now=NOW) == 1.1
    assert ssv.fresh_tick_price(1.1, None, (NOW - timedelta(minutes=10)).replace(tzinfo=None), now=NOW) is None
    monkeypatch.setenv("MARKET_TICK_MAX_AGE_SECONDS", "900")
    assert ssv.fresh_tick_price(1.1, None, (NOW - timedelta(minutes=10)).replace(tzinfo=None), now=NOW) == 1.1


def test_tick_without_any_time_or_price_is_rejected():
    assert ssv.fresh_tick_price(1.1, None, None, now=NOW) is None
    assert ssv.fresh_tick_price(0, (NOW.timestamp() * 1000), None, now=NOW) is None
    assert ssv.fresh_tick_price("x", None, None, now=NOW) is None


class _Row:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Session:
    def __init__(self, row):
        self.row = row
        self.sql = []

    async def execute(self, statement, params=None):
        self.sql.append(str(statement))
        return _Row(self.row)


def _install(monkeypatch, row, yf_price):
    import db.session

    session = _Session(row)

    @contextlib.asynccontextmanager
    async def fake_session(**_kwargs):
        yield session

    monkeypatch.setattr(db.session, "get_session", fake_session)

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url):
            return types.SimpleNamespace(status_code=400, json=lambda: {})

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    class _Ticker:
        def __init__(self, symbol):
            self.fast_info = types.SimpleNamespace(last_price=yf_price)

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=_Ticker))
    return session


def test_live_price_skips_a_stale_tick_and_uses_the_next_source(monkeypatch):
    july = datetime(2026, 7, 2, 17, 57, 9)
    session = _install(monkeypatch, (0.85679, int(july.replace(tzinfo=timezone.utc).timestamp() * 1000), july), 0.8347)
    price = asyncio.run(ssv._get_live_price_async("EURGBP"))
    assert price == pytest.approx(0.8347)
    assert "updated_at" in session.sql[0]


def test_live_price_uses_a_fresh_tick(monkeypatch):
    now = datetime.now(timezone.utc)
    _install(monkeypatch, (0.8346, int(now.timestamp() * 1000), now.replace(tzinfo=None)), 9.99)
    assert asyncio.run(ssv._get_live_price_async("EURGBP")) == pytest.approx(0.8346)
