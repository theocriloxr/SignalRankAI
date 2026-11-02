"""Signal detail chart candles (2 Nov 2026)."""
from __future__ import annotations

import asyncio
from datetime import datetime

from web import platform_api


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Session:
    def __init__(self, rows):
        self.rows, self.params = rows, None

    async def execute(self, statement, params):
        self.params = params
        return _Result(self.rows)


def test_chart_window_and_shape():
    session = _Session([(1793570400000, 1.0, 1.2, 0.9, 1.1), (1793574000000, None, 1.2, 0.9, 1.1)])
    row = {"asset": "btcusdt", "timeframe": "24h", "created_at": datetime(2026, 11, 1, 12, 0)}
    chart = asyncio.run(platform_api._signal_chart_candles(session, row))
    assert chart["timeframe"] == "1d" and session.params["s"] == "BTCUSDT" and session.params["tf"] == "1d"
    assert session.params["b"] - session.params["a"] <= 300 * 86_400_000
    assert chart["candles"] == [{"t": 1793570400000, "o": 1.0, "h": 1.2, "l": 0.9, "c": 1.1}]


def test_chart_unsupported_timeframe_and_failure():
    assert asyncio.run(platform_api._signal_chart_candles(_Session([]), {"timeframe": "7w", "created_at": datetime.now()}))[
        "reason"] == "timeframe_unsupported"

    class Broken:
        async def execute(self, *a, **k):
            raise RuntimeError("db down")

    out = asyncio.run(platform_api._signal_chart_candles(Broken(), {"timeframe": "1h", "asset": "X",
                                                                    "created_at": datetime.now()}))
    assert out["candles"] == [] and out["reason"] == "candles_unavailable"
