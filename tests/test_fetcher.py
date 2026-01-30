import unittest
from unittest.mock import patch

import data.fetcher as fetcher


def make_candles(n=200):
    out = []
    ts = 1600000000000
    for i in range(n):
        out.append({
            "timestamp": ts + i * 60000,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10.0,
        })
    return out


class FetcherTest(unittest.TestCase):
    @patch('data.fetcher.get_crypto_candles')
    def test_get_candles_crypto_single_provider(self, mock_get_crypto):
        mock_get_crypto.return_value = make_candles(200)
        # force single-provider mode
        with patch.dict('os.environ', {'USE_MULTI_PROVIDER_DATA': 'false'}):
            candles = fetcher.get_candles('BTCUSDT', '1h')
            self.assertIsInstance(candles, list)
            self.assertGreaterEqual(len(candles), 20)

    @patch('data.fetcher.get_asset_type')
    def test_get_candles_handles_exception(self, mock_asset_type):
        # simulate get_asset_type raising an error; get_candles should catch and return []
        mock_asset_type.side_effect = Exception('boom')
        candles = fetcher.get_candles('X', '1h')
        self.assertEqual(candles, [])


if __name__ == '__main__':
    unittest.main()
