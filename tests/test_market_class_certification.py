from __future__ import annotations

import asyncio
import time
import argparse
import json
from datetime import datetime, timezone
import pytest

from scripts import certify_market_classes as certification


@pytest.fixture(autouse=True)
def open_session_clock(monkeypatch):
    # Candle age and the real calendar use one fixed Tuesday during US cash hours.
    monkeypatch.setattr(time, "time", lambda: datetime(2026, 10, 6, 14, tzinfo=timezone.utc).timestamp())


@pytest.mark.parametrize("classes,timeout", [("", 1), (", ,", 1), ("crypto_spot,crypto_spot", 1), ("crypto_spot", 0), ("crypto_spot", -1), ("crypto_spot", float("nan")), ("crypto_spot", float("inf"))])
def test_invalid_certification_scope_cannot_report_success(monkeypatch, tmp_path, classes, timeout):
    monkeypatch.setenv("SIGNALRANK_ENVIRONMENT_OVERRIDE", "production")
    output = tmp_path / "certificate.json"
    args = argparse.Namespace(asset_classes=classes, timeout=timeout, output=str(output), allow_non_release_environment=False)
    with pytest.raises(RuntimeError):
        asyncio.run(certification._run(args))
    assert not output.exists()


@pytest.mark.parametrize("eligible", ["false", "true", 1, False, None])
def test_non_boolean_provider_result_cannot_become_certified(monkeypatch, tmp_path, eligible):
    monkeypatch.setenv("SIGNALRANK_ENVIRONMENT_OVERRIDE", "production")
    async def certify(*args):
        return {"execution_eligible": eligible}
    monkeypatch.setattr(certification, "_certify", certify)
    output = tmp_path / "certificate.json"
    args = argparse.Namespace(asset_classes="crypto_spot", timeout=1, output=str(output), allow_non_release_environment=False)
    assert asyncio.run(certification._run(args)) == 4
    report = json.loads(output.read_text())
    assert report["all_required_classes_execution_eligible"] is False
    assert report["all_supported_classes_execution_eligible"] is False


def test_subset_pass_is_distinct_from_all_supported_classes_pass(monkeypatch, tmp_path):
    monkeypatch.setenv("SIGNALRANK_ENVIRONMENT_OVERRIDE", "production")
    async def certify(*args):
        return {"execution_eligible": True}
    monkeypatch.setattr(certification, "_certify", certify)
    output = tmp_path / "certificate.json"
    args = argparse.Namespace(asset_classes="crypto_spot", timeout=1, output=str(output), allow_non_release_environment=False)
    assert asyncio.run(certification._run(args)) == 0
    report = json.loads(output.read_text())
    assert report["all_required_classes_execution_eligible"] is True
    assert report["all_supported_classes_execution_eligible"] is False
    args.asset_classes = ",".join(certification.CLASS_SAMPLES)
    assert asyncio.run(certification._run(args)) == 0
    assert json.loads(output.read_text())["all_supported_classes_execution_eligible"] is True


def _fresh_rows(count: int = 30, step: int = 300) -> list[dict]:
    end = int(time.time())
    start = end - ((count - 1) * step)
    return [
        {
            "timestamp": (start + index * step) * 1000,
            "open": 100.0 + index,
            "high": 101.0 + index,
            "low": 99.0 + index,
            "close": 100.5 + index,
            "volume": 1000.0,
        }
        for index in range(count)
    ]


def test_market_class_certification_accepts_fresh_named_provider(monkeypatch) -> None:
    async def fetch(symbol: str, timeframe: str):
        return _fresh_rows()

    monkeypatch.setattr(certification, "async_get_candles", fetch)
    monkeypatch.setattr(
        certification,
        "_get_last_provider_used",
        lambda symbol, timeframe: "oanda_connector",
    )
    result = asyncio.run(
        certification._certify("forex", "EURUSD", "5m", 2.0)
    )
    assert result["status"] == "PASS"
    assert result["execution_eligible"] is True
    assert result["provider"] == "oanda_connector"


@pytest.mark.parametrize("environment", ["staging", "production", "test"])
@pytest.mark.parametrize("provider", ["yfinance", "yfinance_connector", "yahoo_legacy"])
def test_market_class_certification_rejects_yfinance(monkeypatch, environment, provider) -> None:
    monkeypatch.setenv("SIGNALRANK_ENVIRONMENT_OVERRIDE", environment)
    async def fetch(symbol: str, timeframe: str):
        return _fresh_rows()

    monkeypatch.setattr(certification, "async_get_candles", fetch)
    monkeypatch.setattr(
        certification,
        "_get_last_provider_used",
        lambda symbol, timeframe: provider,
    )
    result = asyncio.run(
        certification._certify("commodity_spot", "XAUUSD", "5m", 2.0)
    )
    assert result["status"] == "FAILED"
    assert result["execution_eligible"] is False
    assert "analysis_only_provider" in result["reasons"]


def test_market_class_certification_rejects_stale_payload(monkeypatch) -> None:
    rows = _fresh_rows()
    for row in rows:
        row["timestamp"] -= 24 * 3600 * 1000

    async def fetch(symbol: str, timeframe: str):
        return rows

    monkeypatch.setattr(certification, "async_get_candles", fetch)
    monkeypatch.setattr(
        certification,
        "_get_last_provider_used",
        lambda symbol, timeframe: "twelvedata_connector",
    )
    result = asyncio.run(
        certification._certify("equity", "AAPL", "5m", 2.0)
    )
    assert result["status"] == "FAILED"
    assert result["execution_eligible"] is False
    assert any(reason.startswith("stale:") for reason in result["reasons"])


def test_release_environment_is_required(monkeypatch) -> None:
    for name in (
        "SIGNALRANK_ENVIRONMENT_OVERRIDE",
        "RAILWAY_ENVIRONMENT_NAME",
        "RAILWAY_ENVIRONMENT",
        "APP_ENV",
        "ENVIRONMENT",
    ):
        monkeypatch.delenv(name, raising=False)
    assert certification._environment() == ""


@pytest.mark.parametrize("provider,reason", [
    ("invented_connector", "provider_not_in_catalog"),
    ("cache_forward_fill", "provider_not_in_catalog"),
    ("ecb_connector", "provider_capability_mismatch"),
    ("binance_connector", "provider_capability_mismatch"),
])
def test_certification_rejects_unqualified_forex_sources(monkeypatch, provider, reason):
    async def fetch(*args):
        return _fresh_rows()
    monkeypatch.setattr(certification, "async_get_candles", fetch)
    monkeypatch.setattr(certification, "_get_last_provider_used", lambda *args: provider)
    result = asyncio.run(certification._certify("forex", "EURUSD", "5m", 2.0))
    assert result["execution_eligible"] is False
    assert reason in result["reasons"]


def test_certification_rejects_future_dated_candles(monkeypatch):
    async def fetch(*args):
        rows = _fresh_rows()
        for row in rows:
            row["timestamp"] += 3600 * 1000
        return rows
    monkeypatch.setattr(certification, "async_get_candles", fetch)
    monkeypatch.setattr(certification, "_get_last_provider_used", lambda *args: "oanda_connector")
    result = asyncio.run(certification._certify("forex", "EURUSD", "5m", 2.0))
    assert result["execution_eligible"] is False
    assert "future_timestamp" in result["reasons"]


@pytest.mark.parametrize("asset_class,symbol,provider", [
    ("forex", "EURUSD", "twelvedata_connector"),
    ("equity", "AAPL", "polygon_connector"),
    ("index", "NAS100", "twelvedata_connector"),
    ("commodity_spot", "XAUUSD", "twelvedata_connector"),
])
def test_fresh_candles_on_closed_weekend_cannot_certify_execution(monkeypatch, asset_class, symbol, provider):
    monkeypatch.setattr(time, "time", lambda: datetime(2026, 10, 11, 16, tzinfo=timezone.utc).timestamp())
    async def fetch(*args):
        return _fresh_rows()
    monkeypatch.setattr(certification, "async_get_candles", fetch)
    monkeypatch.setattr(certification, "_get_last_provider_used", lambda *args: provider)
    result = asyncio.run(certification._certify(asset_class, symbol, "5m", 2.0))
    assert result["validation"]["valid"] is True and result["age_seconds"] == 0
    assert result["execution_eligible"] is False and result["status"] == "FAILED"
    assert result["market_session"]["is_open"] is False
    assert "market_closed" in result["reasons"]


def test_continuous_crypto_can_certify_on_weekend(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: datetime(2026, 10, 11, 16, tzinfo=timezone.utc).timestamp())
    async def fetch(*args):
        return _fresh_rows()
    monkeypatch.setattr(certification, "async_get_candles", fetch)
    monkeypatch.setattr(certification, "_get_last_provider_used", lambda *args: "coinbase_connector")
    result = asyncio.run(certification._certify("crypto_spot", "BTCUSDT", "5m", 2.0))
    assert result["execution_eligible"] is True and result["status"] == "PASS"
    assert result["market_session"]["is_open"] is True


def test_calendar_failure_cannot_certify_fresh_provider_data(monkeypatch):
    async def fetch(*args):
        return _fresh_rows()
    def unavailable(*args, **kwargs):
        raise RuntimeError("calendar unavailable")
    monkeypatch.setattr(certification, "async_get_candles", fetch)
    monkeypatch.setattr(certification, "_get_last_provider_used", lambda *args: "oanda_connector")
    monkeypatch.setattr(certification, "get_market_session_status", unavailable)
    result = asyncio.run(certification._certify("forex", "EURUSD", "5m", 2.0))
    assert result["execution_eligible"] is False and result["status"] == "FAILED"
    assert "market_session_unavailable" in result["reasons"]
    assert result["market_session"]["error_type"] == "RuntimeError"
