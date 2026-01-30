import asyncio
import unittest
from unittest.mock import patch


class _DummyResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


class _DummyClient:
    def __init__(self, payload):
        self._payload = payload

    async def get(self, *args, **kwargs):
        return _DummyResp(self._payload, status=200)


class TestProviderAdapters(unittest.TestCase):
    def test_polygon_adapter_parses_results(self):
        sample = {"results": [{"t": 1700000000000, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 100} for _ in range(30)]}

        async def run_test():
            import os
            os.environ["POLYGON_API_KEY"] = "fake"
            with patch("utils.httpx_client.get_client", return_value=_DummyClient(sample)):
                async def wrapper(fn, **k):
                    return await fn()
                with patch("utils.httpx_client.retry_async", new=wrapper):
                    from data.connectors.polygon_adapter import _async_get_candles
                    out = await _async_get_candles("TESTSYM", "1h")
                    self.assertIsInstance(out, list)
                    self.assertGreaterEqual(len(out), 1)

        asyncio.run(run_test())

    def test_twelvedata_adapter_parses_values(self):
        values = [{"datetime": "2024-01-01T00:00:00", "open": "1", "high": "2", "low": "0.5", "close": "1.5", "volume": "100"} for _ in range(30)]
        sample = {"values": values}

        async def run_test():
            import os
            os.environ["TWELVEDATA_API_KEY"] = "fake"
            with patch("utils.httpx_client.get_client", return_value=_DummyClient(sample)):
                async def wrapper(fn, **k):
                    return await fn()
                with patch("utils.httpx_client.retry_async", new=wrapper):
                    from data.connectors.twelvedata_adapter import _async_get_candles
                    out = await _async_get_candles("TEST", "1h")
                    self.assertIsInstance(out, list)
                    self.assertGreaterEqual(len(out), 1)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
