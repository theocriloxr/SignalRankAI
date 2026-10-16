"""Run with the isolated SDK interpreter: python -m unittest discover -s tests_sdk.

These tests exercise installed vendor parsers and request models against
controlled transports, without account credentials or external connections.
"""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sdk_worker", ROOT / "market_data_sdk/worker.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
logging.disable(logging.CRITICAL)


class InstalledSDKTests(unittest.TestCase):
    def test_alpaca_real_request_models_and_response_parser(self):
        import requests
        calls = []
        def request(_session, method, url, **kwargs):
            calls.append((method, url, kwargs))
            response = requests.Response()
            response.status_code = 200
            symbol = "BTC/USDT" if "/crypto/" in url else "AAPL"
            response._content = json.dumps({"bars": {symbol: [dict(t="2026-01-01T00:00:00Z",
                o=10, h=12, l=9, c=11, v=5, n=2, vw=10.5)]}, "next_page_token": None}).encode()
            return response
        with patch.dict("os.environ", {"ALPACA_API_KEY": "test", "ALPACA_API_SECRET": "test"}), \
                patch.object(requests.Session, "request", request):
            rows = worker.alpaca_bars(dict(symbol="AAPL", timeframe="4h", limit=2, feed="iex"), 5)
            self.assertEqual(rows[0]["close"], 11)
            self.assertEqual(calls[0][2]["params"]["feed"], "iex")
            self.assertEqual(calls[0][2]["params"]["sort"], "desc")
            crypto = worker.alpaca_bars(dict(symbol="BTC/USDT", timeframe="5m", limit=2, crypto=True), 5)
            self.assertEqual(crypto[0]["close"], 11)
            self.assertIn("BTC/USDT", str(calls[-1][2]["params"]))

    def test_marketdata_real_http_transport_and_dataclass_parser(self):
        import httpx
        from marketdata import MarketDataClient
        calls = []
        clients = []
        def handler(request):
            calls.append(request)
            payload = {} if request.url.path.endswith("user/") else dict(s="ok", t=[1_800_000_000],
                o=[10], h=[12], l=[9], c=[11], v=[5])
            response = httpx.Response(200, request=request, json=payload, headers={
                "x-api-ratelimit-limit": "100", "x-api-ratelimit-remaining": "99",
                "x-api-ratelimit-reset": "1800000100", "x-api-ratelimit-consumed": "1"})
            response.elapsed = timedelta(milliseconds=1)
            return response
        def client(instance):
            result = httpx.Client(base_url="https://api.marketdata.app", headers=instance.headers,
                                  transport=httpx.MockTransport(handler))
            clients.append(result)
            return result
        with patch.dict("os.environ", {"MARKETDATA_TOKEN": "test"}), \
                patch.object(MarketDataClient, "_get_client", client):
            rows = worker.marketdata_bars(dict(symbol="AAPL", timeframe="5m", limit=2, mode="live"), 5)
        self.assertEqual(rows[0]["close"], 11)
        self.assertEqual(rows[0]["timestamp"], 1_800_000_000_000)
        self.assertIn("/stocks/candles/5/AAPL/", calls[-1].url.path)
        self.assertEqual(calls[-1].url.params["mode"], "live")
        self.assertTrue(all(c.is_closed for c in clients))

    def test_ccxt_real_kraken_parser_and_active_market_check(self):
        import ccxt
        def load(instance):
            instance.set_markets([dict(id="XBTUSDT", symbol="BTC/USDT", base="BTC", quote="USDT",
                baseId="XBT", quoteId="USDT", type="spot", spot=True, active=True)])
        def fetch(instance, url, method="GET", headers=None, body=None):
            self.assertIn("api.kraken.com", url)
            self.assertIn("pair=XBTUSDT", url)
            return {"error": [], "result": {"XBTUSDT": [[1_800_000_000, "10", "12", "9", "11", "10", "5", 2]]}}
        with patch.object(ccxt.kraken, "load_markets", load), patch.object(ccxt.kraken, "fetch", fetch):
            rows = worker.ccxt_bars(dict(symbol="BTC/USDT", timeframe="5m", limit=2, venue="kraken"), 5)
            self.assertEqual(rows[0]["volume"], 5)
            with self.assertRaises(ValueError):
                worker.ccxt_bars(dict(symbol="ETH/USDT", timeframe="5m", limit=2, venue="kraken"), 5)

    def test_ibapi_real_client_callback_contract_without_order_methods(self):
        from ibapi.client import EClient
        from ibapi.common import BarData
        from ibapi.wrapper import EWrapper
        calls = []
        def connect(instance, host, port, clientId):
            calls.append((host, port, clientId))
            instance.nextValidId(1)
        def history(instance, reqId, contract, *args):
            self.assertEqual(contract.secType, "STK")
            bar = BarData()
            bar.date, bar.open, bar.high, bar.low, bar.close, bar.volume = "1800000000", 10, 12, 9, 11, 5
            instance.historicalData(reqId, bar)
            instance.historicalDataEnd(reqId, "", "")
        def market_data(instance, reqId, *args):
            instance.marketDataType(reqId, 1)
        with patch.object(EClient, "connect", connect), patch.object(EClient, "run", lambda *_: None), \
             patch.object(EClient, "reqMarketDataType", lambda *_: None), \
             patch.object(EClient, "reqMktData", market_data), \
             patch.object(EClient, "cancelMktData", lambda *_: None), \
             patch.object(EClient, "reqHistoricalData", history), \
             patch.object(EClient, "placeOrder", side_effect=AssertionError("orders forbidden")):
            rows = worker.ibkr_bars(dict(symbol="AAPL", timeframe="5m", limit=2, host="127.0.0.1",
                port=4002, client_id=71, contract=dict(symbol="AAPL", secType="STK", exchange="SMART", currency="USD")), 2)
        self.assertEqual(rows[0]["close"], 11)
        self.assertEqual(calls, [("127.0.0.1", 4002, 71)])
        self.assertTrue(callable(EWrapper.marketDataType))

    def test_ibapi_rejects_delayed_market_data_type(self):
        from ibapi.client import EClient
        def connect(instance, *args, **kwargs):
            instance.nextValidId(1)
        def delayed(instance, reqId, *args):
            instance.marketDataType(reqId, 3)
        with patch.object(EClient, "connect", connect), patch.object(EClient, "run", lambda *_: None), \
             patch.object(EClient, "reqMarketDataType", lambda *_: None), \
             patch.object(EClient, "reqMktData", delayed), \
             patch.object(EClient, "reqHistoricalData", side_effect=AssertionError("must not request history")), \
             self.assertRaisesRegex(ValueError, "realtime_entitlement_not_confirmed"):
            worker.ibkr_bars(dict(symbol="AAPL", timeframe="5m", limit=2, host="127.0.0.1", port=4002,
                client_id=71, contract=dict(symbol="AAPL", secType="STK", exchange="SMART", currency="USD")), 2)

    def test_websocket_real_dependency_and_quote_freshness(self):
        import websocket
        now = datetime.now(timezone.utc).isoformat()
        stream = SimpleNamespace(send=lambda *_: None, settimeout=lambda *_: None, close=lambda: None,
            recv=lambda: json.dumps(dict(type="ticker", product_id="BTC-USDT", best_bid="99",
                                        best_ask="101", price="100", time=now, sequence=1)))
        with patch.object(websocket, "create_connection", return_value=stream) as connect:
            quote = worker.coinbase_quote({"symbol": "BTC-USDT"}, 2)
            self.assertEqual(quote["symbol"], "BTC-USDT")
            self.assertEqual(quote["bid"], 99)
            self.assertEqual(connect.call_args.args[0], "wss://ws-feed.exchange.coinbase.com")
        stream.recv = lambda: json.dumps(dict(type="ticker", product_id="BTC-USDT", best_bid="99",
            best_ask="101", price="100", time="2020-01-01T00:00:00Z"))
        with patch.object(websocket, "create_connection", return_value=stream), self.assertRaises(ValueError):
            worker.coinbase_quote({"symbol": "BTC-USDT"}, 2)
        stream.recv = lambda: json.dumps(dict(type="ticker", product_id="BTC-USDT", best_bid="99",
            best_ask="101", price="100", time=datetime.now(timezone.utc).replace(tzinfo=None).isoformat()))
        with patch.object(websocket, "create_connection", return_value=stream), \
             self.assertRaisesRegex(ValueError, "ambiguous_stream_timezone"):
            worker.coinbase_quote({"symbol": "BTC-USDT"}, 2)


if __name__ == "__main__":
    unittest.main()
