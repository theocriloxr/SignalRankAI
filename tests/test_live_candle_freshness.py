"""Current-data boundaries reject unusable bars while retaining historical validation."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from data import connector_registry, fetcher
from data.provider_catalog import evaluate_candle_freshness, validate_candles

NOW = 1_800_000_000.0


def rows(age=30.0):
    return [{"timestamp": NOW - age - (24 - i) * 300, "open": 100,
             "high": 101, "low": 99, "close": 100, "volume": 1} for i in range(25)]


@pytest.fixture(autouse=True)
def isolated_current_data(monkeypatch):
    monkeypatch.setattr(fetcher.time, "time", lambda: NOW)
    monkeypatch.setattr(fetcher, "_CANDLE_CACHE", {})
    monkeypatch.setattr(fetcher, "_CANDLE_INFLIGHT", {})
    monkeypatch.setattr(fetcher, "_LAST_PROVIDER_USED", {})
    monkeypatch.setenv("OHLC_MAX_PROVIDER_ATTEMPTS_PER_TIMEFRAME", "5")
    monkeypatch.setenv("USE_MULTI_PROVIDER_DATA", "1")
    monkeypatch.setattr(fetcher, "get_asset_type", lambda _: "stock")


@pytest.mark.parametrize("stamp", [NOW - 30, (NOW - 30) * 1e3, (NOW - 30) * 1e6,
                                  (NOW - 30) * 1e9, str(NOW - 30),
                                  datetime.fromtimestamp(NOW - 30, timezone.utc).isoformat()])
def test_timestamp_units_preserve_actual_candle_age(stamp):
    result = evaluate_candle_freshness({"last_timestamp": stamp}, interval_seconds=300, now_epoch=NOW)
    assert result == {"fresh": True, "age_seconds": 30, "limit_seconds": 750, "reason": ""}


@pytest.mark.parametrize("age,reason", [(750, ""), (750.01, "stale_candles"),
                                      (-30, ""), (-30.01, "future_timestamp")])
def test_explicit_freshness_and_clock_skew_limits(age, reason):
    result = evaluate_candle_freshness({"last_timestamp": NOW - age}, interval_seconds=300, now_epoch=NOW)
    assert result["reason"] == reason
    assert result["fresh"] is (not reason)


@pytest.mark.parametrize("stamp", [None, "", "not a timestamp", float("inf"), float("nan"), 0])
def test_missing_or_nonfinite_timestamps_fail_closed(stamp):
    assert evaluate_candle_freshness({"last_timestamp": stamp}, interval_seconds=300, now_epoch=NOW)["reason"] == "missing_freshness_timestamp"


@pytest.mark.parametrize("interval,clock", [(0, NOW), (-1, NOW), (float("nan"), NOW),
                                          (300, float("inf")), ("bad", NOW), (300, None)])
def test_invalid_observation_clock_fails_closed(interval, clock):
    assert evaluate_candle_freshness({"last_timestamp": NOW}, interval_seconds=interval, now_epoch=clock)["reason"] == "invalid_observation_clock"


def test_historical_windows_remain_valid_at_their_observation_time():
    historical = validate_candles(rows(age=86400), minimum=20)
    assert historical["valid"]
    assert not evaluate_candle_freshness(historical, interval_seconds=300, now_epoch=NOW)["fresh"]
    assert evaluate_candle_freshness(historical, interval_seconds=300, now_epoch=NOW - 86400)["fresh"]


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("failure", ["stale", "future", "invalid"])
def test_invalid_first_provider_falls_back_to_fresh_provider(monkeypatch, asynchronous, failure):
    bad = rows(age=751 if failure == "stale" else -31 if failure == "future" else 30)
    if failure == "invalid":
        bad[10]["high"] = 1
    good = rows()
    attempted = []

    def first(*args, **kwargs):
        attempted.append("first")
        return bad

    def second(*args, **kwargs):
        attempted.append("second")
        return good

    monkeypatch.setattr(fetcher, "provider_is_healthy", lambda _: True)
    monkeypatch.setattr(fetcher, "_provider_timeframe_eligible", lambda *args: True)
    if asynchronous:
        async def async_first(*args, **kwargs):
            return first()
        async def async_second(*args, **kwargs):
            return second()
        monkeypatch.setattr(connector_registry, "get_async_providers_for_asset", lambda _: [("bad_test", async_first), ("good_test", async_second)])
        result = asyncio.run(fetcher.async_get_candles("AAPL", "5m"))
    else:
        result = fetcher._try_provider_chain([("bad_test", first), ("good_test", second)], asset="AAPL", timeframe="5m", asset_kind="stock")
    assert result == good
    assert attempted == ["first", "second"]
    assert fetcher._get_last_provider_used("AAPL", "5m") == "good_test"


def test_recent_cache_write_does_not_make_old_source_bars_fresh(monkeypatch):
    cache = {("AAPL", "5m"): (NOW, rows(age=751))}
    monkeypatch.setattr(fetcher, "_CANDLE_CACHE", cache)
    monkeypatch.setattr(fetcher, "_fetch_stock_multi_provider", lambda *args: [])
    monkeypatch.setenv("CANDLE_FORWARD_FILL_TTL_SECONDS", "600")
    assert fetcher.get_candles("AAPL", "5m") == []


@pytest.mark.parametrize("failure", ["stale", "future", "missing", "invalid"])
def test_market_data_never_calculates_indicators_for_rejected_bars(monkeypatch, failure):
    bars = rows(age=751 if failure == "stale" else -31 if failure == "future" else 30)
    if failure == "missing":
        bars[-1].pop("timestamp")
    elif failure == "invalid":
        bars[10]["low"] = 500
    monkeypatch.setattr(fetcher, "get_candles", lambda *args: bars)
    indicators = Mock(side_effect=AssertionError("invalid bars reached indicators"))
    monkeypatch.setattr(fetcher, "calculate_indicators", indicators)
    assert fetcher.fetch_market_data("AAPL", ["5m"]) == {}
    indicators.assert_not_called()


def test_market_data_reports_source_age_without_rewriting_bars(monkeypatch):
    bars = rows()
    monkeypatch.setattr(fetcher, "get_candles", lambda *args: bars)
    monkeypatch.setattr(fetcher, "calculate_indicators", lambda _: {"rsi": 50})
    monkeypatch.setattr(fetcher, "validate_price_sanity", lambda *args: True)
    fetcher._set_last_provider_used("AAPL", "5m", "polygon_connector")
    result = fetcher.fetch_market_data("AAPL", ["5m"])["5m"]
    assert result["candles"] == bars
    assert result["latest_candle_timestamp"] == NOW - 30
    assert result["candle_age_seconds"] == 30
    assert result["source"] == "polygon_connector"
    assert result["stale_but_acceptable"] is False
