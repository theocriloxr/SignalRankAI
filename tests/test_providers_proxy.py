import sys
from types import SimpleNamespace


def test_binance_ccxt_uses_http_proxy(monkeypatch):
    import data.providers as providers

    calls = {}

    class DummyExchange:
        def __init__(self, config):
            calls["config"] = config

        def fetch_ohlcv(self, *args, **kwargs):
            return [[1, 2, 3, 4, 5, 6]]

    dummy_ccxt = SimpleNamespace(binance=DummyExchange)
    monkeypatch.setitem(sys.modules, "ccxt", dummy_ccxt)
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.local:8080")

    rows = providers._fetch_binance_ccxt_sync("BTCUSDT", "1h", limit=10)

    assert rows and rows[0]["close"] == 5.0
    assert calls["config"]["proxy"] == "http://proxy.local:8080"
    assert calls["config"]["proxies"]["https"] == "http://proxy.local:8080"