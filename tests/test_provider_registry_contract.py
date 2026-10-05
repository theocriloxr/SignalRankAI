from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from data import connector_registry as registry, fetcher


@pytest.mark.parametrize("kind,variable", [("crypto", "CRYPTO_MARKET_DATA_PROVIDERS"),
    ("fx", "FX_MARKET_DATA_PROVIDERS"), ("stock", "STOCK_MARKET_DATA_PROVIDERS"),
    ("index", "INDEX_MARKET_DATA_PROVIDERS"), ("commodity", "COMMODITY_MARKET_DATA_PROVIDERS")])
@pytest.mark.parametrize("asynchronous", [False, True])
def test_configured_allowlist_is_ordered_deduplicated_and_excludes_legacy(monkeypatch, kind, variable, asynchronous):
    allowed = "coinbase,okx,coinbase" if kind == "crypto" else "fcs,twelvedata,fcs"
    monkeypatch.setenv(variable, allowed)
    monkeypatch.setenv("FCS_API_KEY", "registry-local-test")
    monkeypatch.setenv("TWELVEDATA_API_KEY", "registry-local-test")
    get = registry.get_async_providers_for_asset if asynchronous else registry.get_providers_for_asset
    names = [name for name, _ in get(kind)]
    assert names == (["coinbase_connector", "okx_connector"] if kind == "crypto" else ["fcs_connector", "twelvedata_connector"])


@pytest.mark.parametrize("raw", ["unknown", "polygon", "fcs"])
def test_unavailable_explicit_provider_cannot_enable_other_sources(monkeypatch, raw):
    for key in ("POLYGON_API_KEY", "MASSIVE_API_KEY", "FCS_API_KEY", "FCS_API_SECRET"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("FX_MARKET_DATA_PROVIDERS", raw)
    assert registry.get_providers_for_asset("fx") == []
    assert registry.get_async_providers_for_asset("fx") == []


@pytest.mark.parametrize("asynchronous", [False, True])
def test_wrapper_honors_timeout_and_required_limit_without_duplicate_calls(asynchronous):
    calls = []
    def provider(symbol, tf, *, limit, timeout):
        calls.append((symbol, tf, limit, timeout))
        raise TypeError("internal parse failure")
    if asynchronous:
        async def native(symbol, tf, *, limit, timeout):
            return provider(symbol, tf, limit=limit, timeout=timeout)
        with pytest.raises(TypeError, match="internal parse failure"):
            asyncio.run(registry._wrap_to_async(native)("AAPL", "5m", timeout=3))
    else:
        assert registry._wrap_callable(provider)("AAPL", "5m", timeout=3) == []
    assert calls == [("AAPL", "5m", 200, 3)]


@pytest.mark.parametrize("kind,function", [("crypto", "_fetch_crypto_multi_provider"),
    ("fx", "_fetch_fx_multi_provider"), ("stock", "_fetch_stock_multi_provider"),
    ("index", "_fetch_index_multi_provider"), ("commodity", "_fetch_commodity_multi_provider")])
def test_every_sync_path_consumes_the_same_registered_chain(monkeypatch, kind, function):
    calls = []
    monkeypatch.setattr(registry, "get_providers_for_asset", lambda actual: calls.append(actual) or [])
    assert getattr(fetcher, function)("TEST", "5m") == []
    assert calls == [kind]


def test_explicit_order_precedes_health_and_timeframe_filter_precedes_budget(monkeypatch):
    monkeypatch.setenv("FX_MARKET_DATA_PROVIDERS", "fcs,twelvedata")
    monkeypatch.setenv("OHLC_MAX_PROVIDER_ATTEMPTS_PER_TIMEFRAME", "1")
    monkeypatch.setattr(fetcher, "provider_is_healthy", lambda name: name == "twelvedata_connector")
    candidates = [("ecb_connector", object()), ("fcs_connector", object()), ("twelvedata_connector", object())]
    assert [name for name, _ in fetcher._ordered_provider_candidates(candidates, asset_kind="fx", timeframe="5m")] == ["fcs_connector"]
