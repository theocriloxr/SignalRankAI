"""Bybit V5 request signatures match what is actually sent (1 Nov 2026).

Bybit signs ``timestamp + api_key + recv_window + payload`` with HMAC-SHA256,
where payload is the exact query string of a GET or the exact JSON body of a
POST, and verifies it against the request it receives. The client signed a
sorted query but let httpx send the parameters in insertion order, so any GET
whose keys were not already sorted (order status, closed P&L) was rejected
with "error sign" on a real key. Offline: an httpx MockTransport records the
wire request; no network, no real key.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal

import httpx
import pytest

from services.bybit_client import BybitCredentials, BybitV5Client

KEY, SECRET = "unit-test-key", "unit-test-secret"


def _expected_signature(request: httpx.Request) -> str:
    payload = request.url.query.decode() if request.method == "GET" else request.content.decode()
    material = (request.headers["X-BAPI-TIMESTAMP"] + KEY + request.headers["X-BAPI-RECV-WINDOW"] + payload)
    return hmac.new(SECRET.encode(), material.encode(), hashlib.sha256).hexdigest()


def _client(seen: list[httpx.Request], result: dict) -> BybitV5Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"retCode": 0, "retMsg": "OK", "result": result})

    return BybitV5Client(BybitCredentials(KEY, SECRET, testnet=True),
                         client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.mark.asyncio
@pytest.mark.parametrize("call", [
    lambda c: c.get_wallet_balance(coin="usdt"),
    lambda c: c.get_positions(symbol="btcusdt"),
    lambda c: c.get_order(symbol="btcusdt", order_link_id="sr-123"),
    lambda c: c.get_order(symbol="btcusdt", order_id="9f1c", order_link_id="sr-123"),
    lambda c: c.get_closed_pnl(symbol="btcusdt", start_time_ms=1_761_955_200_000, end_time_ms=1_762_041_600_000),
    lambda c: c.get_api_key_info(),
], ids=["wallet", "positions", "order_by_link", "order_by_both", "closed_pnl", "api_key_info"])
async def test_get_signature_covers_the_query_actually_sent(call):
    seen: list[httpx.Request] = []
    client = _client(seen, {"list": [{"symbol": "BTCUSDT"}]})
    try:
        await call(client)
    except Exception:
        pass  # parsing of the canned result is not under test here
    signed = [r for r in seen if "X-BAPI-SIGN" in r.headers]
    assert signed, "no authenticated request was made"
    for request in signed:
        assert request.headers["X-BAPI-SIGN"] == _expected_signature(request), request.url
        assert request.headers["X-BAPI-API-KEY"] == KEY


@pytest.mark.asyncio
async def test_public_market_data_is_sent_unsigned_with_its_query():
    seen: list[httpx.Request] = []
    client = _client(seen, {"list": [{"symbol": "ETHUSDT", "lastPrice": "2500"}]})
    await client.get_ticker("ethusdt")
    (request,) = seen
    assert "X-BAPI-SIGN" not in request.headers and "X-BAPI-API-KEY" not in request.headers
    assert request.url.query.decode() == "category=linear&symbol=ETHUSDT"


@pytest.mark.asyncio
async def test_post_signature_covers_the_exact_body():
    seen: list[httpx.Request] = []
    client = _client(seen, {"orderId": "1", "orderLinkId": "sr-1"})
    try:
        await client._request("POST", "/v5/order/create", body={"category": "linear", "symbol": "BTCUSDT",
                                                                  "side": "Buy", "qty": str(Decimal("0.001"))})
    except Exception:
        pass
    (request,) = seen
    assert request.headers["X-BAPI-SIGN"] == _expected_signature(request)
    assert json.loads(request.content) == {"category": "linear", "symbol": "BTCUSDT", "side": "Buy", "qty": "0.001"}
