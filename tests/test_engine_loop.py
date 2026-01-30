import unittest
from unittest.mock import patch


class EngineLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_once_collects_signals(self):
        fake_market = {"1h": {"candles": [{"time": 1, "open": 1, "high": 2, "low": 0.5, "close": 1.5}], "indicators": {}}}

        with patch("data.fetcher.fetch_market_data", return_value=fake_market):
            from engine.loop import run_once

            res = await run_once(["XAUUSD", "XAGUSD"], ["1h"], include_ml=False)
            # Should produce a mapping for each asset (strategy may return empty list)
            self.assertIn("XAUUSD", res)
            self.assertIn("XAGUSD", res)


if __name__ == "__main__":
    unittest.main()
