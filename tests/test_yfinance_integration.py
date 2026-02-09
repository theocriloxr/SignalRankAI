import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import datetime, timedelta

from data.market_data import (
    _convert_to_yfinance_symbol,
    _fetch_via_yfinance,
    get_realtime_price,
)


class TestYfinanceIntegration(unittest.TestCase):
    def test_convert_to_yfinance_symbol_crypto(self):
        """Test crypto symbol conversion."""
        self.assertEqual(_convert_to_yfinance_symbol("BTCUSDT"), "BTC-USD")
        self.assertEqual(_convert_to_yfinance_symbol("ETHUSDT"), "ETH-USD")
        self.assertEqual(_convert_to_yfinance_symbol("SOLUSDT"), "SOL-USD")

    def test_convert_to_yfinance_symbol_fx(self):
        """Test FX symbol conversion."""
        self.assertEqual(_convert_to_yfinance_symbol("EURUSD"), "EURUSD=X")
        self.assertEqual(_convert_to_yfinance_symbol("GBPUSD"), "GBPUSD=X")
        self.assertEqual(_convert_to_yfinance_symbol("USDJPY"), "USDJPY=X")

    def test_convert_to_yfinance_symbol_commodity(self):
        """Test commodity symbol conversion."""
        self.assertEqual(_convert_to_yfinance_symbol("XAUUSD"), "GC=F")
        self.assertEqual(_convert_to_yfinance_symbol("XAGUSD"), "SI=F")
        self.assertEqual(_convert_to_yfinance_symbol("WTIUSD"), "CL=F")
        self.assertEqual(_convert_to_yfinance_symbol("CRUDEOIL"), "CL=F")
        self.assertEqual(_convert_to_yfinance_symbol("NATGAS"), "NG=F")

    def test_convert_to_yfinance_symbol_stock(self):
        """Test stock symbol conversion (no change)."""
        self.assertEqual(_convert_to_yfinance_symbol("AAPL"), "AAPL")
        self.assertEqual(_convert_to_yfinance_symbol("TSLA"), "TSLA")
        self.assertEqual(_convert_to_yfinance_symbol("MSFT"), "MSFT")

    @patch('data.market_data.yf.Ticker')
    def test_fetch_via_yfinance_success(self, mock_ticker_class):
        """Test successful data fetch via yfinance."""
        # Create mock DataFrame - use lowercase 'h' for hourly frequency
        dates = pd.date_range(start=datetime.now() - timedelta(days=30), periods=100, freq='1h')
        mock_df = pd.DataFrame({
            'Open': [100.0] * 100,
            'High': [102.0] * 100,
            'Low': [98.0] * 100,
            'Close': [101.0] * 100,
            'Volume': [1000.0] * 100,
        }, index=dates)

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_df
        mock_ticker_class.return_value = mock_ticker

        # Test fetch
        candles = _fetch_via_yfinance("BTCUSDT", "1h", 100)

        # Verify
        self.assertIsInstance(candles, list)
        self.assertEqual(len(candles), 100)
        self.assertIn('open', candles[0])
        self.assertIn('high', candles[0])
        self.assertIn('low', candles[0])
        self.assertIn('close', candles[0])
        self.assertIn('volume', candles[0])
        self.assertIn('timestamp', candles[0])

    @patch('data.market_data.yf.Ticker')
    def test_fetch_via_yfinance_empty_response(self, mock_ticker_class):
        """Test handling of empty yfinance response."""
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_class.return_value = mock_ticker

        candles = _fetch_via_yfinance("INVALID", "1h", 100)
        self.assertEqual(candles, [])

    @patch('data.market_data.yf.Ticker')
    def test_fetch_via_yfinance_exception(self, mock_ticker_class):
        """Test exception handling in yfinance fetch."""
        mock_ticker_class.side_effect = Exception("Network error")

        candles = _fetch_via_yfinance("BTCUSDT", "1h", 100)
        self.assertEqual(candles, [])

    @patch('data.market_data.yf.Ticker')
    def test_get_realtime_price_success(self, mock_ticker_class):
        """Test successful realtime price fetch."""
        mock_ticker = MagicMock()
        mock_ticker.fast_info = {'lastPrice': 50000.0}
        mock_ticker_class.return_value = mock_ticker

        price = get_realtime_price("BTCUSDT")
        self.assertIsNotNone(price)
        self.assertEqual(price, 50000.0)

    @patch('data.market_data.yf.Ticker')
    @patch('requests.get')
    def test_get_realtime_price_fallback_to_binance(self, mock_requests, mock_ticker_class):
        """Test fallback to Binance when yfinance fails."""
        # yfinance fails
        mock_ticker_class.side_effect = Exception("yfinance error")

        # Binance succeeds
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"price": "45000.0"}
        mock_requests.return_value = mock_response

        price = get_realtime_price("BTCUSDT")
        self.assertIsNotNone(price)
        self.assertEqual(price, 45000.0)

    @patch('data.market_data.yf.Ticker')
    def test_get_realtime_price_failure(self, mock_ticker_class):
        """Test realtime price returns None when all sources fail."""
        mock_ticker_class.side_effect = Exception("All sources failed")

        price = get_realtime_price("INVALID")
        self.assertIsNone(price)


if __name__ == '__main__':
    unittest.main()
