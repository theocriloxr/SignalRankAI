from __future__ import annotations

import asyncio
import time

from scripts import certify_market_classes as certification


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


def test_market_class_certification_rejects_yfinance(monkeypatch) -> None:
    async def fetch(symbol: str, timeframe: str):
        return _fresh_rows()

    monkeypatch.setattr(certification, "async_get_candles", fetch)
    monkeypatch.setattr(
        certification,
        "_get_last_provider_used",
        lambda symbol, timeframe: "yfinance",
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
