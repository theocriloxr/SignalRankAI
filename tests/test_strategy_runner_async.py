import asyncio
import unittest
from unittest.mock import patch


class AsyncRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_runner_calls_strategy(self):
        class FakeAsyncStrategy:
            def __init__(self):
                self.last = None

            async def generate(self, market_data):
                self.last = market_data
                return ["ok"]

        fake_market = {"1h": {"candles": [{"time": 1, "open": 1, "high": 2, "low": 0.5, "close": 1.5}]}}

        with patch("data.fetcher.fetch_market_data", return_value=fake_market):
            from engine.strategies.runner import run_strategy_with_marketstate_async

            s = FakeAsyncStrategy()
            out = await run_strategy_with_marketstate_async(s, "XAUUSD", ["1h"], include_ml=False)
            self.assertEqual(out, ["ok"])
            self.assertIsNotNone(s.last)


if __name__ == "__main__":
    asyncio.run(unittest.main())
