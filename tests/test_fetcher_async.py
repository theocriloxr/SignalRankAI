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

    def test_async_get_candles_crypto_fallback_chain_binance_403_bybit_timeout_cryptocompare_success(self):
        calls = []

        async def binance_403(symbol, tf, timeout=10):
            calls.append("binance")
            raise RuntimeError("HTTP 403 geo blocked")

        async def bybit_timeout(symbol, tf, timeout=10):
            calls.append("bybit")
            raise asyncio.TimeoutError("bybit timeout")

        async def cryptocompare_ok(symbol, tf, timeout=10):
            calls.append("cryptocompare")
            return make_dummy_candles(30)

        async def retry_once(fn, retries=3, backoff=1.0, *args, **kwargs):
            return await fn()

        async def run_test():
            with patch(
                "data.connector_registry.get_async_providers_for_asset",
                return_value=[
                    ("binance_connector", binance_403),
                    ("bybit_connector", bybit_timeout),
                    ("cryptocompare_connector", cryptocompare_ok),
                ],
            ), patch("data.fetcher.retry_async_httpx", new=retry_once):
                from data.fetcher import async_get_candles
                out = await async_get_candles("BTCUSDT", "1h")
                self.assertGreaterEqual(len(out), 20)
                self.assertEqual(calls, ["binance", "bybit", "cryptocompare"])

        asyncio.run(run_test())

    def test_all_provider_failures_do_not_break_asset_loop(self):
        async def run_test():
            from engine.core import _fetch_market_data_for_assets

            async def fake_fetch(asset, tfs):
                if asset == "BTCUSDT":
                    return {}
                return {"1h": {"candles": make_dummy_candles(30), "indicators": {"ok": True}}}

            with patch("engine.core.fetch_market_data_cached", side_effect=fake_fetch):
                with self.assertLogs("engine.core", level="WARNING") as logs:
                    out = await _fetch_market_data_for_assets({"BTCUSDT": ["1h"], "ETHUSDT": ["1h"]})
                self.assertEqual(out.get("BTCUSDT"), {})
                self.assertTrue(out.get("ETHUSDT"))
                self.assertTrue(
                    any("All providers failed for BTCUSDT, skipping..." in msg for msg in logs.output)
                )

        asyncio.run(run_test())

    def test_fetch_candles_waterfall_falls_back_to_multi_provider_fetcher(self):
        from data.providers import fetch_candles_waterfall

        fallback_candles = make_dummy_candles(25)

        with patch("data.providers.fetch_binance_ccxt_candles", return_value=[]), patch(
            "data.fetcher.get_candles", return_value=fallback_candles
        ):
            out = fetch_candles_waterfall("BTCUSDT", "1h", limit=20)

        self.assertEqual(len(out), 20)
        self.assertEqual(out[-1]["close"], fallback_candles[19]["close"])


if __name__ == "__main__":
    unittest.main()
