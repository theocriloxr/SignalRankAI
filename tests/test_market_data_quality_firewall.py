from __future__ import annotations

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
