import unittest
from unittest.mock import patch

import data.news as news


class _MockResp:
    def __init__(self, ok=True, payload=None):
        self.ok = ok
        self._payload = payload or {}

    def json(self):
        return self._payload


class TestNewsXSentiment(unittest.TestCase):
    def setUp(self):
        news._NEWS_CACHE.clear()

    @patch("data.news.requests.get")
    def test_fetch_news_headlines_uses_x_bearer(self, mock_get):
        mock_get.return_value = _MockResp(
            ok=True,
            payload={
                "data": [
                    {
                        "text": "Bitcoin rally continues with strong momentum",
                        "created_at": "2026-04-09T12:00:00Z",
                    }
                ]
            },
        )

        with patch.dict("os.environ", {"NEWSAPI_KEY": "", "X_BEARER_TOKEN": "token-123"}, clear=False):
            rows = news.fetch_news_headlines("BTCUSDT", lookback_minutes=60)

        self.assertEqual(len(rows), 1)
        title, published_at, score = rows[0]
        self.assertIn("Bitcoin rally", title)
        self.assertEqual(published_at, "2026-04-09T12:00:00Z")
        self.assertGreaterEqual(score, 1)
        called_url = mock_get.call_args[0][0]
        self.assertIn("api.twitter.com/2/tweets/search/recent", called_url)

    @patch("data.news.requests.get")
    def test_fetch_news_headlines_without_x_token_skips_x_for_non_crypto(self, mock_get):
        with patch.dict("os.environ", {"NEWSAPI_KEY": "", "X_BEARER_TOKEN": ""}, clear=False):
            rows = news.fetch_news_headlines("EURUSD", lookback_minutes=60)

        self.assertEqual(rows, [])
        for call in mock_get.call_args_list:
            self.assertNotIn("api.twitter.com/2/tweets/search/recent", call[0][0])

    @patch("data.news.requests.get")
    def test_x_failure_falls_back_to_cryptocompare(self, mock_get):
        def side_effect(url, *args, **kwargs):
            if "api.twitter.com/2/tweets/search/recent" in url:
                raise RuntimeError("x api failure")
            if "cryptocompare.com" in url:
                return _MockResp(
                    ok=True,
                    payload={
                        "Data": [
                            {
                                "title": "BTC breakout",
                                "body": "bullish follow-through",
                                "published_on": 1712664000,
                            }
                        ]
                    },
                )
            return _MockResp(ok=False, payload={})

        mock_get.side_effect = side_effect

        with patch.dict("os.environ", {"NEWSAPI_KEY": "", "X_BEARER_TOKEN": "token-xyz"}, clear=False):
            rows = news.fetch_news_headlines("BTCUSDT", lookback_minutes=60)

        self.assertEqual(len(rows), 1)
        self.assertIn("BTC breakout", rows[0][0])

    @patch("data.news.requests.get")
    def test_fetch_news_headlines_uses_cryptopanic(self, mock_get):
        def side_effect(url, *args, **kwargs):
            if "cryptopanic.com" in url:
                return _MockResp(
                    ok=True,
                    payload={
                        "results": [
                            {
                                "title": "Solana rally extends",
                                "published_at": "2026-04-09T12:10:00Z",
                                "currencies": [{"code": "SOL"}],
                            }
                        ]
                    },
                )
            return _MockResp(ok=False, payload={})

        mock_get.side_effect = side_effect

        with patch.dict(
            "os.environ",
            {"NEWSAPI_KEY": "", "X_BEARER_TOKEN": "", "CRYPTOPANIC_TOKEN": "cp-123", "ALPHAVANTAGE_API_KEY": ""},
            clear=False,
        ):
            rows = news.fetch_news_headlines("SOLUSDT", lookback_minutes=60)

        self.assertEqual(len(rows), 1)
        self.assertIn("Solana rally", rows[0][0])
        called_urls = [call[0][0] for call in mock_get.call_args_list]
        self.assertTrue(any("cryptopanic.com" in url for url in called_urls))

    @patch("data.news.requests.get")
    def test_fetch_news_headlines_uses_alphavantage_news_sentiment(self, mock_get):
        def side_effect(url, *args, **kwargs):
            if "alphavantage.co/query" in url:
                return _MockResp(
                    ok=True,
                    payload={
                        "feed": [
                            {
                                "title": "EURUSD steady after inflation print",
                                "time_published": "20260409T121500",
                                "summary": "forex sentiment remains neutral",
                                "ticker_sentiment": [
                                    {"ticker_sentiment_score": "1.0"},
                                ],
                            }
                        ]
                    },
                )
            return _MockResp(ok=False, payload={})

        mock_get.side_effect = side_effect

        with patch.dict(
            "os.environ",
            {"NEWSAPI_KEY": "", "X_BEARER_TOKEN": "", "CRYPTOPANIC_TOKEN": "", "ALPHAVANTAGE_API_KEY": "av-123"},
            clear=False,
        ):
            rows = news.fetch_news_headlines("EURUSD", lookback_minutes=60)

        self.assertEqual(len(rows), 1)
        self.assertIn("EURUSD steady", rows[0][0])
        called_urls = [call[0][0] for call in mock_get.call_args_list]
        self.assertTrue(any("alphavantage.co/query" in url for url in called_urls))


if __name__ == "__main__":
    unittest.main()
