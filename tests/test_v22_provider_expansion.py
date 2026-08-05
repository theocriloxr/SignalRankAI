"""V2.2 provider expansion regression + contract tests.

Covers:
* provider activation state machine (data/provider_activation.py)
* catalog integrity (every implemented spec resolves a callable)
* Massive/Polygon credential consolidation
* keyless public adapter contract tests (mocked HTTP)
* dormant credential adapters (missing_credentials, zero exceptions)
* dynamic instrument discovery registry (data/instrument_discovery.py)
"""
from __future__ import annotations

import asyncio
import importlib

import pytest

from data.provider_activation import (
    ProviderActivationState,
    execution_mode,
    resolve_activation,
)


# --------------------------------------------------------------------------- #
# Activation state machine
# --------------------------------------------------------------------------- #
class TestActivationStateMachine:
    def test_disabled_when_flag_off(self):
        act = resolve_activation(provider="coingecko", public_endpoint=True, env={"COINGECKO_ENABLED": "0"})
        assert act.state is ProviderActivationState.DISABLED
        assert not act.market_data_ready
        assert not act.execution_ready

    def test_public_ready_keyless(self):
        act = resolve_activation(
            provider="coingecko", public_endpoint=True, default_enabled=True,
            env={"COINGECKO_ENABLED": "1"},
        )
        assert act.state is ProviderActivationState.PUBLIC_READY
        assert act.market_data_ready
        assert not act.execution_ready
        assert act.can_serve_analysis

    def test_missing_credentials_is_normal(self):
        act = resolve_activation(
            provider="fred", required_env=("FRED_API_KEY",), default_enabled=True, env={}
        )
        assert act.state is ProviderActivationState.MISSING_CREDENTIALS
        assert not act.market_data_ready
        assert act.reason.startswith("missing_credentials")

    def test_healthy_with_credentials(self):
        act = resolve_activation(
            provider="fred", required_env=("FRED_API_KEY",), default_enabled=True,
            env={"FRED_API_KEY": "secret"},
        )
        assert act.state is ProviderActivationState.HEALTHY
        assert act.market_data_ready

    def test_credentials_never_enable_execution(self):
        act = resolve_activation(
            provider="alpaca",
            required_env=("ALPACA_API_KEY", "ALPACA_API_SECRET"),
            default_enabled=True,
            env={"ALPACA_API_KEY": "k", "ALPACA_API_SECRET": "s"},
        )
        assert act.market_data_ready
        assert not act.execution_ready

    def test_execution_flag_without_certification_blocked(self):
        act = resolve_activation(
            provider="hyperliquid",
            required_env=("HYPERLIQUID_API_WALLET_ADDRESS",),
            execution_flag_env="HYPERLIQUID_MAINNET_EXECUTION_ENABLED",
            execution_certification_env="HYPERLIQUID_EXECUTION_CERTIFICATION_ID",
            env={
                "HYPERLIQUID_ENABLED": "1",
                "HYPERLIQUID_API_WALLET_ADDRESS": "0xabc",
                "HYPERLIQUID_MAINNET_EXECUTION_ENABLED": "live",
            },
        )
        assert act.state is ProviderActivationState.PLAN_INSUFFICIENT
        assert not act.execution_ready

    def test_execution_requires_certification_and_allowlist(self):
        act = resolve_activation(
            provider="hyperliquid",
            required_env=("HYPERLIQUID_API_WALLET_ADDRESS",),
            execution_flag_env="HYPERLIQUID_MAINNET_EXECUTION_ENABLED",
            execution_certification_env="HYPERLIQUID_EXECUTION_CERTIFICATION_ID",
            allowlist_env="HYPERLIQUID_INSTRUMENT_ALLOWLIST",
            env={
                "HYPERLIQUID_ENABLED": "1",
                "HYPERLIQUID_API_WALLET_ADDRESS": "0xabc",
                "HYPERLIQUID_MAINNET_EXECUTION_ENABLED": "live_guarded",
                "HYPERLIQUID_EXECUTION_CERTIFICATION_ID": "cert-1",
                "HYPERLIQUID_INSTRUMENT_ALLOWLIST": "BTCUSDT,ETHUSDT",
            },
        )
        assert act.execution_ready
        assert act.market_data_ready

    def test_suspended_and_circuit_overrides(self):
        act = resolve_activation(provider="okx", public_endpoint=True, env={"OKX_SUSPENDED": "1"})
        assert act.state is ProviderActivationState.SUSPENDED
        act = resolve_activation(provider="okx", public_endpoint=True, env={"OKX_CIRCUIT_OPEN": "1"})
        assert act.state is ProviderActivationState.CIRCUIT_OPEN
        act = resolve_activation(provider="okx", public_endpoint=True, env={"OKX_RATE_LIMITED": "1"})
        assert act.state is ProviderActivationState.RATE_LIMITED

    def test_execution_mode_resolution(self, monkeypatch):
        monkeypatch.setenv("REAL_EXECUTION_ENABLED", "0")
        monkeypatch.setenv("PAPER_TRADING_ENABLED", "1")
        assert execution_mode() == "paper"
        monkeypatch.setenv("TESTNET_EXECUTION_ENABLED", "1")
        assert execution_mode() == "testnet"
        monkeypatch.setenv("REAL_EXECUTION_ENABLED", "1")
        assert execution_mode() == "live_guarded"


# --------------------------------------------------------------------------- #
# Catalog + registry integrity
# --------------------------------------------------------------------------- #
class TestCatalogIntegrity:
    def test_every_implemented_spec_resolves(self):
        from data.provider_catalog import list_provider_specs

        specs = list_provider_specs(implemented_only=True)
        assert len(specs) >= 25
        for spec in specs:
            assert spec.resolve_connector() is not None, f"{spec.key} connector missing"

    def test_new_provider_specs_present(self):
        from data.provider_catalog import list_provider_specs

        keys = {s.key for s in list_provider_specs()}
        for key in (
            "coingecko", "coinmetrics", "defillama", "fred", "trading_economics",
            "coinglass", "dune", "kaiko", "glassnode", "cryptoquant",
        ):
            assert key in keys, f"catalog missing {key}"

    def test_connectors_package_exports_new_functions(self):
        import data.connectors as c

        for name in (
            "coingecko_get_candles", "coingecko_discover_instruments",
            "coinmetrics_get_candles", "defillama_discover_instruments",
            "fred_fetch_series", "trading_economics_fetch_calendar",
            "coinglass_get_funding", "dune_query_result", "kaiko_get_ohlcv",
            "glassnode_onchain_metric", "cryptoquant_onchain_metric",
        ):
            assert callable(getattr(c, name, None)), f"{name} not exported"

    def test_connector_modules_import_cleanly(self):
        for module in (
            "data.connectors.coingecko_adapter",
            "data.connectors.coinmetrics_adapter",
            "data.connectors.defillama_adapter",
            "data.connectors.fred_adapter",
            "data.connectors.trading_economics_adapter",
            "data.connectors.coinglass_adapter",
            "data.connectors.dune_adapter",
            "data.connectors.kaiko_adapter",
            "data.connectors.glassnode_adapter",
            "data.connectors.cryptoquant_adapter",
        ):
            importlib.import_module(module)


# --------------------------------------------------------------------------- #
# Massive / Polygon consolidation
# --------------------------------------------------------------------------- #
class TestMassiveAlias:
    def test_massive_key_preferred(self, monkeypatch):
        import data.connectors.polygon_adapter as poly

        monkeypatch.setenv("MASSIVE_API_KEY", "massive-key")
        monkeypatch.setenv("POLYGON_API_KEY", "polygon-key")
        assert poly._resolved_api_key() == "massive-key"

    def test_polygon_alias_fallback(self, monkeypatch):
        import data.connectors.polygon_adapter as poly

        monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
        monkeypatch.setenv("POLYGON_API_KEY", "polygon-key")
        assert poly._resolved_api_key() == "polygon-key"

    def test_base_url_override(self, monkeypatch):
        import data.connectors.polygon_adapter as poly

        monkeypatch.setenv("MASSIVE_API_BASE_URL", "https://api.massive.com")
        assert poly._resolved_base_url() == "https://api.massive.com"
        monkeypatch.delenv("MASSIVE_API_BASE_URL", raising=False)
        assert poly._resolved_base_url() == "https://api.polygon.io"

    def test_registry_accepts_massive_key(self, monkeypatch):
        from data.connector_registry import _provider_configured

        monkeypatch.setenv("MASSIVE_API_KEY", "k")
        monkeypatch.delenv("POLYGON_API_KEY", raising=False)
        assert _provider_configured("polygon_connector")


# --------------------------------------------------------------------------- #
# Keyless adapter contract tests (mocked HTTP)
# --------------------------------------------------------------------------- #
async def _noop_json(*args, **kwargs):
    return None


def _patch_json(monkeypatch, module, payload):
    async def _fake(url, *, name, params=None, headers=None, timeout=8.0, retries=2):
        return payload

    monkeypatch.setattr(module, "async_http_get_json", _fake)


class TestCoinGeckoContract:
    def test_candles_ohlc_parsing(self, monkeypatch):
        import data.connectors.coingecko_adapter as cg

        monkeypatch.setattr(cg, "_COOLDOWN_UNTIL", {})
        cg._symbol_to_id_cache().clear()

        async def _resolve(symbol):
            return "bitcoin"

        monkeypatch.setattr(cg, "_async_resolve_id", _resolve)
        payload = [[1672531200000, 16000.0, 16100.0, 15900.0, 16050.0]]
        _patch_json(monkeypatch, cg, payload)
        rows = asyncio.run(cg._async_get_candles("BTCUSDT", "1d", limit=5))
        assert len(rows) == 1
        assert rows[0]["timestamp"] == 1672531200
        assert rows[0]["close"] == 16050.0

    def test_price_parsing(self, monkeypatch):
        import data.connectors.coingecko_adapter as cg

        monkeypatch.setattr(cg, "_COOLDOWN_UNTIL", {})

        async def _resolve(symbol):
            return "bitcoin"

        monkeypatch.setattr(cg, "_async_resolve_id", _resolve)
        _patch_json(monkeypatch, cg, {"bitcoin": {"usd": 50000.0}})
        price = asyncio.run(cg._async_get_price("BTCUSDT"))
        assert price == 50000.0

    def test_discovery_normalization(self, monkeypatch):
        import data.connectors.coingecko_adapter as cg

        monkeypatch.setattr(cg, "_COOLDOWN_UNTIL", {})
        _patch_json(
            monkeypatch, cg,
            [{"id": "bitcoin", "symbol": "btc", "market_cap": 1e12, "total_volume": 1e10}],
        )
        rows = asyncio.run(cg._async_discover_instruments(top=1))
        assert rows[0]["provider_symbol"] == "BTCUSDT"
        assert rows[0]["asset_class"] == "crypto"
        assert rows[0]["instrument_type"] == "spot"

    def test_health_never_network(self):
        import data.connectors.coingecko_adapter as cg

        info = cg.health()
        assert info["provider_id"] == "coingecko"
        assert info["use_for_execution_quote"] is False


class TestCoinMetricsContract:
    def test_candles_parsing(self, monkeypatch):
        import data.connectors.coinmetrics_adapter as cm

        _patch_json(
            monkeypatch, cm,
            {"data": [{"time": 1672531200, "price_open": 100.0, "price_high": 102.0,
                       "price_low": 99.0, "price_close": 101.0, "volume": 1000.0}]},
        )
        rows = asyncio.run(cm._async_get_candles("BTCUSDT", "1d", limit=5))
        assert len(rows) == 1
        assert rows[0]["open"] == 100.0
        assert rows[0]["close"] == 101.0

    def test_network_metric(self, monkeypatch):
        import data.connectors.coinmetrics_adapter as cm

        _patch_json(monkeypatch, cm, {"data": [{"time": 1672531200, "AdrActCnt": "12345"}]})
        result = asyncio.run(cm._async_get_network_metric("BTC", "AdrActCnt"))
        assert result["metric"] == "AdrActCnt"
        assert result["AdrActCnt"] == "12345"


class TestDefiLlamaContract:
    def test_stablecoin_totals(self, monkeypatch):
        import data.connectors.defillama_adapter as dl

        _patch_json(monkeypatch, dl, [{"totalCirculatingUSD": {"peggedUSD": 1.6e11}}])
        result = asyncio.run(dl._async_stablecoin_totals())
        assert result["source"] == "stablecoins.llama.fi"
        assert result["points"] == 1

    def test_discovery(self, monkeypatch):
        import data.connectors.defillama_adapter as dl

        _patch_json(
            monkeypatch, dl,
            {"peggedAssets": [{"symbol": "usdc", "pegType": "peggedUSD", "chains": ["ethereum"]}]},
        )
        rows = asyncio.run(dl._async_discover_instruments(top=10))
        assert rows[0]["provider_symbol"] == "USDCUSDT"
        assert rows[0]["metadata"]["source"] == "stablecoins"


# --------------------------------------------------------------------------- #
# Dormant credential adapters
# --------------------------------------------------------------------------- #
class TestDormantAdapters:
    @pytest.mark.parametrize(
        "module,method,call",
        [
            ("data.connectors.fred_adapter", "fetch_series", lambda m: m.fetch_series("DGS10")),
            ("data.connectors.trading_economics_adapter", "fetch_calendar", lambda m: m.fetch_calendar(country="US")),
            ("data.connectors.coinglass_adapter", "get_funding", lambda m: m.get_funding("BTCUSDT")),
            ("data.connectors.dune_adapter", "query_result", lambda m: m.query_result("123")),
            ("data.connectors.kaiko_adapter", "get_ohlcv", lambda m: m.get_ohlcv("cbse", "btc-usd")),
            ("data.connectors.glassnode_adapter", "onchain_metric", lambda m: m.onchain_metric("BTC", "addresses")),
            ("data.connectors.cryptoquant_adapter", "onchain_metric", lambda m: m.onchain_metric("binance", "flow")),
        ],
    )
    def test_dormant_without_credentials(self, monkeypatch, module, method, call):
        # Ensure no keys are present and enabled flags are off or keyless.
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        monkeypatch.delenv("TRADING_ECONOMICS_API_KEY", raising=False)
        monkeypatch.delenv("COINGLASS_API_KEY", raising=False)
        monkeypatch.delenv("DUNE_API_KEY", raising=False)
        monkeypatch.delenv("KAIKO_API_KEY", raising=False)
        monkeypatch.delenv("GLASSNODE_API_KEY", raising=False)
        monkeypatch.delenv("CRYPTOQUANT_API_KEY", raising=False)
        mod = importlib.import_module(module)
        result = call(mod)  # must not raise and must be empty/None
        assert result in (None, [])
        health = mod.health()
        assert health["provider_id"]
        assert health["state"] in ("disabled", "missing_credentials")

    def test_fred_active_with_key_and_mock(self, monkeypatch):
        import data.connectors.fred_adapter as fred

        monkeypatch.setenv("FRED_ENABLED", "1")
        monkeypatch.setenv("FRED_API_KEY", "k")

        async def _fake(url, *, name, params=None, headers=None, timeout=8.0, retries=2):
            return {"observations": [{"date": "2024-01-01", "value": "4.25",
                                      "realtime_start": "2024-01-01", "realtime_end": "9999-12-31"}]}

        monkeypatch.setattr(fred, "async_http_get_json", _fake)
        rows = fred.fetch_series("DGS10")
        assert len(rows) == 1
        assert rows[0]["value"] == 4.25
        assert fred.health()["state"] == "healthy"


# --------------------------------------------------------------------------- #
# Dynamic instrument discovery registry
# --------------------------------------------------------------------------- #
class TestInstrumentDiscovery:
    def _registry(self):
        from data.instrument_discovery import DynamicInstrumentRegistry

        return DynamicInstrumentRegistry()

    def test_ingest_created_updated_unchanged(self):
        reg = self._registry()
        rows = [{"provider_symbol": "BTCUSDT", "base": "BTC", "quote": "USDT",
                 "asset_class": "crypto", "instrument_type": "spot"}]
        r1 = reg.ingest("okx", rows)
        assert r1.created == 1 and r1.unchanged == 0
        r2 = reg.ingest("okx", rows)
        assert r2.created == 0 and r2.unchanged == 1
        r3 = reg.ingest("okx", [{"provider_symbol": "BTCUSDT", "base": "BTC", "quote": "USDT",
                                 "asset_class": "crypto", "instrument_type": "spot",
                                 "market_status": "suspended"}])
        assert r3.updated == 1

    def test_xaut_and_xau_stay_separate(self):
        reg = self._registry()
        reg.ingest("coingecko", [{"provider_symbol": "XAUTUSDT", "base": "XAUT", "quote": "USDT",
                                  "asset_class": "crypto", "instrument_type": "spot"}])
        reg.ingest("oanda", [{"provider_symbol": "XAUUSD", "base": "XAU", "quote": "USD",
                              "asset_class": "commodity", "instrument_type": "spot"}])
        assert reg.count() == 2
        keys = {i.canonical_key for i in reg.all()}
        assert "crypto:spot:XAUT:USDT:USDT:-:-:-" in keys
        assert "commodity:spot:XAU:USD:USD:-:-:-" in keys

    def test_provider_map_and_resolve(self):
        reg = self._registry()
        reg.ingest("okx", [{"provider_symbol": "BTCUSDT", "base": "BTC", "quote": "USDT",
                            "asset_class": "crypto", "instrument_type": "spot"}])
        reg.ingest("kraken", [{"provider_symbol": "XXBTZUSD", "base": "BTC", "quote": "USD",
                               "asset_class": "crypto", "instrument_type": "spot"}])
        p_map = reg.provider_map("BTCUSDT")
        assert p_map.get("okx") == "BTCUSDT"
        # Alias resolution: XXBTZUSD also resolves to a BTC instrument.
        assert reg.resolve("BTC/USDT") is not None

    def test_universe_gating(self):
        reg = self._registry()
        reg.ingest("okx", [{"provider_symbol": "BTCUSDT", "base": "BTC", "quote": "USDT",
                            "asset_class": "crypto", "instrument_type": "spot"}])
        reg.ingest("oanda", [{"provider_symbol": "XAUUSD", "base": "XAU", "quote": "USD",
                              "asset_class": "commodity", "instrument_type": "spot",
                              "market_status": "suspended"}])
        reg.ingest("okx", [{"provider_symbol": "ETHUSDT", "base": "ETH", "quote": "USDT",
                            "asset_class": "crypto", "instrument_type": "perpetual"}])
        all_u = reg.universe()
        assert len(all_u) == 2  # suspended commodity excluded
        crypto_u = reg.universe(asset_classes=["crypto"])
        assert all(i.id.asset_class.value == "crypto" for i in crypto_u)
        assert reg.universe(min_providers=2) == ()  # nothing covered twice

    def test_run_discovery_provider_isolation(self):
        from data.instrument_discovery import run_discovery

        def ok_provider(*, top=100):
            return [{"provider_symbol": "BTCUSDT", "base": "BTC", "quote": "USDT",
                     "asset_class": "crypto", "instrument_type": "spot"}]

        def broken_provider(*, top=100):
            raise RuntimeError("boom")

        reg = self._registry()
        results = run_discovery(
            {"ok": ok_provider, "broken": broken_provider},
            registry=reg, min_interval_seconds=0.0,
        )
        assert results["ok"].state == "ok"
        assert results["ok"].created == 1
        assert results["broken"].state == "failed"
        assert reg.count() == 1  # broken provider never blocked the good one

    def test_run_discovery_cooldown(self):
        from data.instrument_discovery import run_discovery

        calls = {"n": 0}

        def provider(*, top=100):
            calls["n"] += 1
            return []

        run_discovery({"p": provider}, min_interval_seconds=3600.0)
        run_discovery({"p": provider}, min_interval_seconds=3600.0)
        assert calls["n"] == 1  # second run hit the cooldown

    def test_metrics_snapshot(self):
        reg = self._registry()
        reg.ingest("okx", [{"provider_symbol": "BTCUSDT", "base": "BTC", "quote": "USDT",
                            "asset_class": "crypto", "instrument_type": "spot"}])
        metrics = reg.snapshot_metrics()
        assert metrics["instruments_discovered"] == 1
        assert metrics["instruments_created"] == 1
