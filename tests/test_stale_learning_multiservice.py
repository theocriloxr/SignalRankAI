from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]


def test_core_never_refreshes_a_stale_signal_with_legacy_partial_rebuild():
    source = (ROOT / "engine" / "core.py").read_text(encoding="utf-8")
    delivery_block = source[source.index("async def deliver_all"):]
    assert "Stale signal REFRESHED" not in delivery_block
    assert "schedule_rejected_signal_learning" in delivery_block
    assert 'LEGACY_TRADE_TRACKER_ENABLED", False' in source


def test_rejection_learning_persists_shadow_only_provenance():
    from engine.rejection_learning import persist_rejected_signal_learning

    fake = AsyncMock()
    deduplicator = type("D", (), {"persist_rejection": fake})()
    quote = type(
        "Q",
        (),
        {
            "provider": "okx",
            "quote_kind": "bid_ask",
            "request_id": "req-1",
            "source_age_ms": 100,
            "latency_ms": 20,
        },
    )()
    signal = {
        "signal_id": "sig-1",
        "asset": "LINKUSDT",
        "timeframe": "1h",
        "direction": "short",
        "entry": 8.3,
        "stop_loss": 8.4,
        "take_profit": [8.2, 8.1],
        "score": 95,
    }

    async def run():
        with patch("engine.signal_deduplicator.get_ml_rejection_tracker", return_value=deduplicator):
            assert await persist_rejected_signal_learning(
                signal,
                reason="price drift",
                rejection_type="stale_pre_delivery",
                live_price=8.5,
                quote=quote,
            )

    asyncio.run(run())
    kwargs = fake.await_args.kwargs
    assert kwargs["rejection_type"] == "stale_pre_delivery"
    assert kwargs["features"]["learning_category"] == "SHADOW_REJECTED"
    assert kwargs["features"]["must_not_enter_live_performance"] is True
    assert kwargs["features"]["quote_provider"] == "okx"


def test_kucoin_maps_canonical_symbol_to_exchange_symbol():
    from data.connectors import kucoin_adapter

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {
                "code": "200000",
                "data": [["1700000000", "10", "11", "12", "9", "100"]] * 20,
            }

    class Client:
        def __init__(self):
            self.url = None

        async def get(self, url, timeout=None):
            self.url = url
            return Response()

    client = Client()

    async def run():
        with patch("data.connectors.kucoin_adapter.httpx_client.get_client", return_value=client):
            candles = await kucoin_adapter._async_get_candles("BTCUSDT", "1h", limit=20)
        assert len(candles) == 20
        assert "symbol=BTC-USDT" in client.url

    asyncio.run(run())


def test_ecb_connector_is_daily_analysis_only_without_network_for_intraday():
    from data.connectors.ecb_adapter import _async_get_candles

    assert asyncio.run(_async_get_candles("EURUSD", "1h")) == []


def test_registry_skips_unconfigured_keyed_providers_and_keeps_public_sources():
    from data.connector_registry import get_async_providers_for_asset

    keys = {
        "TWELVEDATA_API_KEY": "",
        "TWELVE_DATA_API_KEY": "",
        "FMP_API_KEY": "",
        "POLYGON_API_KEY": "",
        "ALPHAVANTAGE_API_KEY": "",
        "ALPHA_VANTAGE_API_KEY": "",
        "TIINGO_API_KEY": "",
    }
    with patch.dict(os.environ, keys, clear=False):
        stock = [name for name, _ in get_async_providers_for_asset("stock")]
        crypto = [name for name, _ in get_async_providers_for_asset("crypto")]
    assert stock[0] == "yfinance_connector"
    assert "twelvedata_connector" not in stock
    assert "fmp_connector" not in stock
    assert "kucoin_connector" in crypto


def test_async_fetcher_enforces_default_two_provider_attempt_budget():
    calls: list[str] = []

    async def empty(name):
        async def provider(symbol, timeframe, timeout=1):
            calls.append(name)
            return []
        return provider

    async def run():
        p1 = await empty("one")
        p2 = await empty("two")
        p3 = await empty("three")
        with patch.dict(os.environ, {"OHLC_MAX_PROVIDER_ATTEMPTS_PER_TIMEFRAME": "2"}), patch(
            "data.connector_registry.get_async_providers_for_asset",
            return_value=[("one_connector", p1), ("two_connector", p2), ("three_connector", p3)],
        ):
            from data.fetcher import async_get_candles
            assert await async_get_candles("BTCUSDT", "1h") == []

    asyncio.run(run())
    assert calls == ["one", "two"]


def test_shadow_worker_source_closes_scan_session_before_network_prices():
    source = (ROOT / "engine" / "shadow_outcome_worker.py").read_text(encoding="utf-8")
    assert "async def _load_rows" in source
    assert "async def _evaluate_rows" in source
    load = source[source.index("async def _load_rows"):source.index("async def _evaluate_rows")]
    assert "_get_live_price" not in load


def test_no_secrets_soak_profile_contains_only_non_secret_configuration():
    text = (ROOT / "RAILWAY_24H_SOAK_NO_SECRETS.env").read_text(encoding="utf-8")
    for forbidden in (
        "DATABASE_URL=",
        "REDIS_URL=",
        "TELEGRAM_BOT_TOKEN=",
        "OWNER_TELEGRAM_ID=",
        "GEMINI_API_KEY=",
        "PAYSTACK_SECRET_KEY=",
        "ENCRYPTION_KEY=",
    ):
        assert forbidden not in text
    assert "AUTO_TRADE_ENABLED=0" in text
    assert "LEGACY_TRADE_TRACKER_ENABLED=0" in text
    assert "ASSET_LEARNING_ENABLED=0" in text
    analytics = (ROOT / "deploy" / "railway_roles" / "analytics.env").read_text(encoding="utf-8")
    assert "ASSET_LEARNING_ENABLED=1" in analytics


def test_start_script_supports_all_decomposed_roles():
    source = (ROOT / "start.sh").read_text(encoding="utf-8")
    for role in ("delivery", "outcome", "analytics", "scheduler"):
        assert role in source


def test_optional_market_data_diagnostics_are_phase_scoped(monkeypatch, caplog):
    import asyncio
    from data import market_data

    monkeypatch.setattr(market_data, "_yf_available", lambda: False)
    monkeypatch.setenv("MARKET_CACHE_ENABLED", "0")
    monkeypatch.setattr(market_data, "async_get_candles", lambda *args, **kwargs: asyncio.sleep(0, result=[]))
    with caplog.at_level("INFO"):
        asyncio.run(market_data.fetch_market_data_cached("BTCUSDT", ["4h", "1d"], diagnostic_scope="optional"))
    text = caplog.text
    assert "[market_data][phase_result] phase=optional" in text
    assert "missing_required_timeframe" not in text


def test_missing_key_providers_do_not_consume_registry_slots(monkeypatch):
    from data.connector_registry import get_async_providers_for_asset

    for name in (
        "TWELVEDATA_API_KEY", "TWELVE_DATA_API_KEY", "FMP_API_KEY", "TIINGO_API_KEY",
        "POLYGON_API_KEY", "ALPHAVANTAGE_API_KEY", "ALPHA_VANTAGE_API_KEY",
        "OANDA_API_KEY", "OANDA_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    names = [name for name, _ in get_async_providers_for_asset("stock")]
    assert not any(name.startswith(("twelvedata", "fmp", "tiingo", "polygon", "alphavantage")) for name in names)
    assert "yfinance_connector" in names


def test_fmp_uses_current_stable_chart_endpoint(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock
    from data.connectors import fmp_adapter

    monkeypatch.setenv("FMP_API_KEY", "test-key")
    response = AsyncMock()
    response.status_code = 200
    response.json = lambda: [{"date": "2026-07-24 12:00:00", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}]
    client = AsyncMock()
    client.get.return_value = response
    monkeypatch.setattr(fmp_adapter.httpx_client, "get_client", lambda provider: client)
    rows = asyncio.run(fmp_adapter._async_get_candles("AAPL", "1h", limit=20))
    assert rows and rows[0]["close"] == 10.5
    url = client.get.await_args.args[0]
    assert "/stable/historical-chart/1hour" in url
