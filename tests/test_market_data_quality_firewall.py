from __future__ import annotations

from datetime import datetime, timezone

import data.market_data as market_data
from data.market_data import _validate_ohlcv


def _rows():
    return [
        {"timestamp": 1_700_000_000, "open": 100, "high": 102, "low": 99, "close": 101, "volume": 10},
        {"timestamp": 1_700_000_060, "open": 101, "high": 103, "low": 100, "close": 102, "volume": 11},
    ]


def test_quality_firewall_accepts_well_formed_candles():
    assert _validate_ohlcv(_rows())


def test_quality_firewall_rejects_duplicate_timestamp():
    rows = _rows()
    rows[1]["timestamp"] = rows[0]["timestamp"]
    assert not _validate_ohlcv(rows)


def test_quality_firewall_rejects_impossible_geometry():
    rows = _rows()
    rows[1]["high"] = 99
    assert not _validate_ohlcv(rows)


def test_quality_firewall_rejects_nonfinite_or_nonpositive_price():
    rows = _rows()
    rows[1]["close"] = float("nan")
    assert not _validate_ohlcv(rows)
    rows = _rows()
    rows[1]["low"] = 0
    assert not _validate_ohlcv(rows)


def test_quality_firewall_rejects_invalid_volume_and_partial_timestamps():
    rows = _rows()
    rows[1]["volume"] = -1
    assert not _validate_ohlcv(rows)
    rows = _rows()
    rows[1].pop("timestamp")
    assert not _validate_ohlcv(rows)


def test_cash_session_reopen_grace_expires_after_first_bar(monkeypatch):
    # UK cash opens 08:00 Europe/London. On 2026-09-29 London is UTC+1,
    # so 07:15 UTC is only 15 minutes into the session. The prior session's
    # final 1h candle is still the newest *completed* bar and must be accepted.
    prior_close_bar = int(datetime(2026, 9, 28, 15, 30, tzinfo=timezone.utc).timestamp())
    candles = [{
        "timestamp": prior_close_bar,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 10.0,
    }]

    just_after_open = datetime(2026, 9, 29, 7, 15, tzinfo=timezone.utc).timestamp()
    monkeypatch.setattr(market_data.time, "time", lambda: just_after_open)
    fresh, age = market_data._check_staleness(candles, "1h", asset="UK100")
    assert fresh is True
    assert age > 2 * 3600

    # Once a fresh 1h bar could have completed, the same old payload must fail
    # the normal hard freshness gate.
    after_first_bar = datetime(2026, 9, 29, 8, 15, tzinfo=timezone.utc).timestamp()
    monkeypatch.setattr(market_data.time, "time", lambda: after_first_bar)
    fresh, _ = market_data._check_staleness(candles, "1h", asset="UK100")
    assert fresh is False


def test_continuous_market_does_not_receive_cash_session_grace(monkeypatch):
    old_bar = int(datetime(2026, 9, 28, 15, 30, tzinfo=timezone.utc).timestamp())
    candles = [{
        "timestamp": old_bar,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 10.0,
    }]
    now = datetime(2026, 9, 29, 7, 15, tzinfo=timezone.utc).timestamp()
    monkeypatch.setattr(market_data.time, "time", lambda: now)
    fresh, _ = market_data._check_staleness(candles, "1h", asset="BTCUSDT")
    assert fresh is False
