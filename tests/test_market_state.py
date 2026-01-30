import unittest
from unittest.mock import patch


class MarketStateTests(unittest.TestCase):
    def test_get_market_state_basic(self):
        # Mock fetch_market_data to return deterministic candles and indicators
        fake_market = {
            "1h": {
                "candles": [
                    {"time": 1, "open": 10, "high": 11, "low": 9, "close": 10.5},
                    {"time": 2, "open": 10.5, "high": 12, "low": 10, "close": 11.0},
                ],
                "indicators": {"rsi": 55},
            },
            "1d": {
                "candles": [
                    {"time": 3, "open": 9, "high": 13, "low": 8, "close": 12.0},
                ],
                "indicators": {"rsi": 60},
            },
        }

        with patch("data.fetcher.fetch_market_data", return_value=fake_market):
            from engine.market_state import get_market_state

            ms = get_market_state("BTCUSDT", ["1h", "1d"], include_ml=False)
            self.assertIn("asset", ms)
            self.assertEqual(ms["asset"], "BTCUSDT")
            self.assertIn("1h", ms["timeframes"])
            self.assertIn("1d", ms["timeframes"])
            self.assertEqual(ms["timeframes"]["1h"]["last_close"], 11.0)

    def test_get_market_state_with_ml(self):
        fake_market = {
            "1h": {
                "candles": [
                    {"time": 1, "open": 10, "high": 11, "low": 9, "close": 10.5},
                ],
                "indicators": {},
            }
        }

        with patch("data.fetcher.fetch_market_data", return_value=fake_market):
            with patch("engine.ml.score_signal", return_value=0.73):
                from engine.market_state import get_market_state

                ms = get_market_state("ETHUSD", ["1h"], include_ml=True)
                self.assertIn("ml_score", ms["timeframes"]["1h"])
                self.assertAlmostEqual(ms["timeframes"]["1h"]["ml_score"], 0.73)


if __name__ == "__main__":
    unittest.main()
