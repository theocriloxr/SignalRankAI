from __future__ import annotations

import asyncio
import pytest

from data import fetcher, connector_registry


def _rows():
    return [{"timestamp": 1_700_000_000 + i * 300, "open": 100, "high": 101,
             "low": 99, "close": 100, "volume": 1} for i in range(25)]


@pytest.mark.parametrize("enabled", ["1", "true", "yes", "on", " TRUE "])
def test_sync_configured_provider_is_used_for_boolean_aliases(monkeypatch, enabled):
    monkeypatch.setenv("USE_MULTI_PROVIDER_DATA", enabled)
    monkeypatch.setattr(fetcher, "_CANDLE_CACHE", {})
    monkeypatch.setattr(fetcher, "_CANDLE_INFLIGHT", {})
    monkeypatch.setattr(fetcher, "get_asset_type", lambda _: "fx")
    calls = []
    def provider(*args):
        calls.append("configured")
        return _rows()
    def legacy(*args):
        pytest.fail("configured provider routing fell through to legacy premium FX")
    monkeypatch.setattr(fetcher, "_fetch_fx_multi_provider", provider)
    monkeypatch.setattr(fetcher, "get_fx_candles", legacy)
    assert len(fetcher.get_candles("EURUSD", "5m")) == 25
    assert calls == ["configured"]


@pytest.mark.parametrize("enabled", ["1", "true", "yes", "on", " TRUE "])
def test_async_configured_provider_preserves_lineage(monkeypatch, enabled):
    monkeypatch.setenv("USE_MULTI_PROVIDER_DATA", enabled)
    monkeypatch.setattr(fetcher, "get_asset_type", lambda _: "fx")
    monkeypatch.setattr(fetcher, "_LAST_PROVIDER_USED", {})
    async def provider(*args, **kwargs):
        return _rows()
    monkeypatch.setattr(connector_registry, "get_async_providers_for_asset",
                        lambda _: [("twelvedata_connector", provider)])
    def legacy(*args):
        pytest.fail("async configured routing used legacy synchronous fetcher")
    monkeypatch.setattr(fetcher, "get_candles", legacy)
    rows = asyncio.run(fetcher.async_get_candles("EURUSD", "5m"))
    assert len(rows) == 25
    assert fetcher._get_last_provider_used("EURUSD", "5m") == "twelvedata_connector"


def test_repeated_provider_failure_does_not_extend_forward_fill_lifetime(monkeypatch):
    clock = [100.0]
    cache = {("EURUSD", "5m"): (90.0, _rows())}
    monkeypatch.setattr(fetcher, "_CANDLE_CACHE", cache)
    monkeypatch.setattr(fetcher, "_CANDLE_INFLIGHT", {})
    monkeypatch.setattr(fetcher.time, "time", lambda: clock[0])
    monkeypatch.setenv("USE_MULTI_PROVIDER_DATA", "1")
    monkeypatch.setenv("CANDLE_REQUEST_CACHE_TTL_SECONDS", "1")
    monkeypatch.setenv("CANDLE_FORWARD_FILL_TTL_SECONDS", "30")
    monkeypatch.setattr(fetcher, "get_asset_type", lambda _: "fx")
    monkeypatch.setattr(fetcher, "_fetch_fx_multi_provider", lambda *args: [])
    assert len(fetcher.get_candles("EURUSD", "5m")) == 25
    assert cache[("EURUSD", "5m")][0] == 90.0
    clock[0] = 119.0
    assert len(fetcher.get_candles("EURUSD", "5m")) == 25
    clock[0] = 121.0
    assert fetcher.get_candles("EURUSD", "5m") == []
