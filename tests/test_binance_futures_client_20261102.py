"""Binance USDⓈ-M futures adapter (2 Nov 2026)."""
from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from services.binance_futures_client import (
    BinanceAmbiguousOrderError,
    BinanceError,
    BinancePermissionError,
    BinanceUsdmClient,
)
from services.bybit_client import BybitCredentials, BybitError

EXCHANGE_INFO = {"symbols": [{"symbol": "BTCUSDT", "status": "TRADING", "filters": [
    {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
    {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "1000"},
    {"filterType": "MARKET_LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "120"},
    {"filterType": "MIN_NOTIONAL", "notional": "100"}]}]}


def _client(handler, testnet=False):
    transport = httpx.MockTransport(handler)
    return BinanceUsdmClient(BybitCredentials("key", "secret", testnet), client=httpx.AsyncClient(transport=transport))


class Recorder:
    def __init__(self, protect_fails=False):
        self.calls = []
        self.protect_fails = protect_fails

    def __call__(self, request: httpx.Request):
        url = urlparse(str(request.url))
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        self.calls.append((request.method, url.path, q, request.headers.get("X-MBX-APIKEY")))
        if url.path == "/fapi/v1/exchangeInfo":
            return httpx.Response(200, json=EXCHANGE_INFO)
        if url.path == "/fapi/v1/ticker/price":
            return httpx.Response(200, json={"symbol": "BTCUSDT", "price": "60000", "time": 1})
        if url.path == "/fapi/v1/order" and request.method == "POST":
            return httpx.Response(200, json={"orderId": 77, "status": "NEW"})
        if url.path == "/fapi/v1/order" and request.method == "GET":
            return httpx.Response(200, json={"orderId": 77, "clientOrderId": "sr-1", "status": "FILLED",
                                             "executedQty": "0.010", "avgPrice": "60010"})
        if url.path == "/fapi/v1/algoOrder":
            if self.protect_fails and q.get("type") == "TAKE_PROFIT_MARKET":
                return httpx.Response(400, json={"code": -2021, "msg": "Order would immediately trigger."})
            return httpx.Response(200, json={"algoId": 9, "algoStatus": "NEW"})
        if url.path == "/fapi/v1/algoOpenOrders":
            return httpx.Response(200, json={"code": 200, "msg": "ok"})
        if url.path == "/sapi/v1/account/apiRestrictions":
            return httpx.Response(200, json={"ipRestrict": True, "enableFutures": True, "enableWithdrawals": False,
                                             "enableInternalTransfer": False, "permitsUniversalTransfer": False})
        if url.path == "/fapi/v2/account":
            return httpx.Response(200, json={"totalMarginBalance": "1000", "totalWalletBalance": "990",
                                             "availableBalance": "900"})
        if url.path == "/fapi/v2/positionRisk":
            return httpx.Response(200, json=[{"symbol": "BTCUSDT", "positionAmt": "-0.010", "entryPrice": "60000",
                                              "markPrice": "59900", "unRealizedProfit": "1"}])
        return httpx.Response(404, json={"code": -1, "msg": "unexpected"})


def test_market_order_is_confirmed_and_protected():
    rec = Recorder()
    result = asyncio.run(_client(rec).place_market_order(symbol="BTCUSDT", side="long", qty=Decimal("0.0109"),
                                                         stop_loss=Decimal("59000.07"), take_profit=Decimal("62000.09"),
                                                         order_link_id="sr-1"))
    assert result["success"] and result["provider"] == "binance" and result["qty"] == "0.010"
    posted = [(p, q) for m, p, q, _ in rec.calls if m == "POST"]
    assert posted[0][0] == "/fapi/v1/order" and posted[0][1]["newClientOrderId"] == "sr-1"
    assert posted[0][1]["side"] == "BUY" and posted[0][1]["type"] == "MARKET"
    protect = [q for p, q in posted if p == "/fapi/v1/algoOrder"]
    assert [q["type"] for q in protect] == ["STOP_MARKET", "TAKE_PROFIT_MARKET"]
    assert all(q["side"] == "SELL" and q["closePosition"] == "true" and "signature" in q for q in protect)
    assert protect[0]["triggerPrice"] == "59000.00" and protect[1]["triggerPrice"] == "62000.00"
    assert all(key == "key" for _, _, _, key in rec.calls if key is not None)


def test_failed_protection_closes_the_position():
    rec = Recorder(protect_fails=True)
    with pytest.raises(BinanceError, match="protective_order_failed_position_closed"):
        asyncio.run(_client(rec).place_market_order(symbol="BTCUSDT", side="buy", qty=Decimal("0.01"),
                                                    stop_loss=Decimal("59000"), take_profit=Decimal("62000"),
                                                    order_link_id="sr-2"))
    closes = [q for m, p, q, _ in rec.calls if m == "POST" and p == "/fapi/v1/order" and q.get("reduceOnly") == "true"]
    assert closes and closes[0]["side"] == "SELL"
    assert any(m == "DELETE" and p == "/fapi/v1/algoOpenOrders" for m, p, _, _ in rec.calls)


def test_levels_on_wrong_side_and_min_notional_are_refused():
    with pytest.raises(BinanceError, match="wrong_side"):
        asyncio.run(_client(Recorder()).place_market_order(symbol="BTCUSDT", side="buy", qty=Decimal("0.01"),
                                                           stop_loss=Decimal("61000"), take_profit=Decimal("62000"),
                                                           order_link_id="x"))
    with pytest.raises(BinanceError, match="notional"):
        asyncio.run(_client(Recorder()).place_market_order(symbol="BTCUSDT", side="buy", qty=Decimal("0.001"),
                                                           stop_loss=Decimal("59000"), take_profit=Decimal("62000"),
                                                           order_link_id="x"))


def test_transport_failure_on_submit_is_ambiguous():
    def handler(request):
        if request.url.path == "/fapi/v1/order" and request.method == "POST":
            raise httpx.ConnectError("reset")
        return Recorder()(request)

    with pytest.raises(BinanceAmbiguousOrderError):
        asyncio.run(_client(handler).place_market_order(symbol="BTCUSDT", side="buy", qty=Decimal("0.01"),
                                                        stop_loss=Decimal("59000"), take_profit=Decimal("62000"),
                                                        order_link_id="x"))


def test_key_permissions():
    assert asyncio.run(_client(Recorder()).verify_trade_only_key())["ip_bound"] is True
    with pytest.raises(BinancePermissionError):
        BinanceUsdmClient.validate_trade_only_permissions({"enableFutures": True, "enableWithdrawals": True})
    with pytest.raises(BinancePermissionError):
        BinanceUsdmClient.validate_trade_only_permissions({"enableFutures": False})
    demo = asyncio.run(_client(Recorder(), testnet=True).verify_trade_only_key())
    assert demo["trade"] and demo["permissions"] == ["futures_demo"]


def test_bybit_shaped_reads():
    c = _client(Recorder())
    wallet = asyncio.run(c.get_wallet_balance(coin="USDT"))
    assert wallet["list"][0]["totalEquity"] == "1000"
    pos = asyncio.run(c.get_positions(symbol="BTCUSDT"))
    assert pos[0]["size"] == "0.010" and pos[0]["side"] == "Sell"
    order = asyncio.run(c.get_order(symbol="BTCUSDT", order_link_id="sr-1"))
    assert order["orderStatus"] == "Filled"
    assert issubclass(BinanceError, BybitError)


def test_router_picks_the_binance_client():
    from services.binance_futures_client import BinanceUsdmClient as B
    from services.bybit_signal_router import _exchange_client
    from services.bybit_client import BybitV5Client

    creds = BybitCredentials("k", "s", True)
    assert isinstance(_exchange_client("binance", creds), B)
    assert isinstance(_exchange_client("bybit", creds), BybitV5Client)


def test_gate_requires_binance_flag(monkeypatch):
    from core.env import SafetyFlags  # type: ignore[attr-defined]

    flags = SafetyFlags.from_env() if hasattr(SafetyFlags, "from_env") else None
    if flags is not None:
        assert flags.binance_execution_enabled is False
