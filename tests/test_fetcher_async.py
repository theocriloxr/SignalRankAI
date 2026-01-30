import os
import asyncio
import unittest
from unittest.mock import patch


def make_dummy_candles(n=30):
    now = 1700000000000
    out = []
    for i in range(n):
        out.append({
            "timestamp": now + i * 60000,
            "open": 100 + i,
            "high": 101 + i,
            "low": 99 + i,
            "close": 100 + i,
            "volume": 1000.0,
        })
    return out


class TestAsyncFetcher(unittest.TestCase):
    def test_async_get_candles_success(self):
        async def provider(symbol, tf, timeout=10):
            return make_dummy_candles(30)

        async def run_test():
            with patch("data.connector_registry.get_async_providers_for_asset", return_value=[("mock", provider)]):
                from data.fetcher import async_get_candles
                out = await async_get_candles("BTCUSDT", "1h")
                self.assertIsInstance(out, list)
                self.assertGreaterEqual(len(out), 20)

        asyncio.run(run_test())

    def test_async_get_candles_all_providers_empty(self):
        async def provider_empty(symbol, tf, timeout=10):
            return []

        async def run_test():
            with patch("data.connector_registry.get_async_providers_for_asset", return_value=[("mock", provider_empty)]):
                from data.fetcher import async_get_candles
                out = await async_get_candles("BTCUSDT", "1h")
                self.assertEqual(out, [])

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
