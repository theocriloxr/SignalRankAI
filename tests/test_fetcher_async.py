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

    def test_crypto_registry_prefers_railway_safe_public_providers(self):
        from data.connector_registry import get_async_providers_for_asset

        names = [name for name, _ in get_async_providers_for_asset("crypto")]

        self.assertGreaterEqual(len(names), 5)
        self.assertEqual(names[:5], [
            "bybit_connector",
            "okx_connector",
            "coinbase_connector",
            "kraken_connector",
            "cryptocompare_connector",
        ])
        self.assertTrue(names.index("coingecko_legacy") > names.index("cryptocompare_connector"))
        self.assertNotIn("binance_connector", names)

    def test_binance_market_data_is_opt_in(self):
        from data.connector_registry import get_async_providers_for_asset

        async def run_test():
            with patch.dict(os.environ, {"BINANCE_MARKET_DATA_ENABLED": "1"}, clear=False):
                names = [name for name, _ in get_async_providers_for_asset("crypto")]
            self.assertIn("binance_connector", names)
            self.assertGreater(names.index("binance_connector"), names.index("cryptocompare_connector"))

        asyncio.run(run_test())

    def test_provider_preference_alias_matches_connector_suffix(self):
        from data.fetcher import _prioritize_provider_list

        providers = [("bybit_connector", object()), ("okx_connector", object())]
        ordered = _prioritize_provider_list(providers, "okx")

        self.assertEqual([name for name, _ in ordered], ["okx_connector", "bybit_connector"])

    def test_provider_health_snapshot_tracks_latency_and_error_rate(self):
        import data.fetcher as fetcher

        fetcher._PROVIDER_HEALTH.clear()
        fetcher.mark_provider_result("okx_connector", True, latency_ms=120)
        fetcher.mark_provider_result("okx_connector", False, latency_ms=240)

        snap = fetcher.get_provider_health_snapshot()["okx_connector"]

        self.assertEqual(snap["success_count"], 1)
        self.assertEqual(snap["failure_count"], 1)
        self.assertEqual(snap["avg_latency_ms"], 180)
        self.assertEqual(snap["error_rate"], 0.5)

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


if __name__ == "__main__":
    unittest.main()
