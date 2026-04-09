import unittest
from unittest.mock import patch, MagicMock

import pandas as pd


class TestConnectorsAndValidators(unittest.TestCase):
    def test_validate_candles(self):
        from core.validators import validate_candles

        self.assertFalse(validate_candles([]))
        self.assertFalse(validate_candles([{"nope": 1}]))
        good = [{"time": 1, "open": 1, "high": 2, "low": 0.5, "close": 1.5}]
        self.assertTrue(validate_candles(good))

    def test_yfinance_adapter_with_mocked_history(self):
        from data.connectors.yfinance_adapter import get_candles

        # Build a small DataFrame with expected columns
        idx = pd.date_range("2023-01-01", periods=3, freq="h")
        df = pd.DataFrame(
            {
                "Open": [100, 101, 102],
                "High": [110, 111, 112],
                "Low": [90, 91, 92],
                "Close": [105, 106, 107],
                "Volume": [1000, 1200, 1100],
            },
            index=idx,
        )

        class DummyTicker:
            def history(self, period, interval):
                return df

        with patch("data.connectors.yfinance_adapter.yf") as mock_yf:
            mock_yf.Ticker.return_value = DummyTicker()
            out = get_candles("BTCUSDT", "1h", limit=2)
            self.assertIsInstance(out, list)
            self.assertGreaterEqual(len(out), 1)
            for c in out:
                self.assertIn("open", c)
                self.assertIn("close", c)

    def test_binance_adapter_with_mocked_requests(self):
        from data.connectors.binance_adapter import get_candles

        sample_payload = [
            [1620000000000, "100", "110", "90", "105", "1000"],
            [1620003600000, "105", "115", "95", "110", "1200"],
        ]

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = sample_payload

        with patch("data.connectors.binance_adapter.requests.get", return_value=mock_resp), \
             patch("data.connectors.binance_adapter.httpx_client.get_client", return_value=None):
            out = get_candles("BTCUSDT", "1h", limit=10)
            self.assertIsInstance(out, list)
            self.assertEqual(len(out), 2)
            self.assertEqual(out[0]["open"], 100.0)


if __name__ == "__main__":
    unittest.main()
