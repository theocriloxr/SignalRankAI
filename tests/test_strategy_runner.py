import unittest
from unittest.mock import patch


class StrategyRunnerTests(unittest.TestCase):
    def test_runner_invokes_strategy(self):
        # Simple fake strategy with a generate that records received market_data
        class FakeStrategy:
            def __init__(self):
                self.last = None

            def generate(self, market_data):
                self.last = market_data
                return []

        fake_market = {"1h": {"candles": [{"time": 1, "open": 1, "high": 2, "low": 0.5, "close": 1.5}]}}

        with patch("data.fetcher.fetch_market_data", return_value=fake_market):
            from engine.strategies.runner import run_strategy_with_marketstate

            s = FakeStrategy()
            out = run_strategy_with_marketstate(s, "XAUUSD", ["1h"], include_ml=False)
            self.assertEqual(out, [])
            self.assertIsNotNone(s.last)
            self.assertIn("1h", s.last)


if __name__ == "__main__":
    unittest.main()
