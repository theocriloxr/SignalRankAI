"""Authenticated Binance USDⓈ-M futures client with the Bybit client's interface (2 Nov 2026).

``services/bybit_signal_router.py`` drives execution through a small client
interface (key verification, wallet, instrument rules, ticker, positions, order
placement and confirmation, closed PnL). This client implements the same
interface for Binance USDⓈ-M perpetual futures, returning Bybit-shaped
dictionaries, so both exchanges go through one admission, sizing, policy,
idempotency and ledger path.

Order placement:

1. a MARKET order with ``newClientOrderId`` (the idempotency key);
2. confirmation through ``GET /fapi/v1/order`` before success is reported;
3. protective STOP_MARKET and TAKE_PROFIT_MARKET orders with
   ``closePosition=true`` through the Algo Order service
   (``POST /fapi/v1/algoOrder``, where Binance now hosts conditional orders);
4. if either protective order is rejected, the position is closed at market
   immediately and the attempt fails, so a position is never left without a
   stop.

API keys must not allow withdrawals or internal transfers; live keys must be
IP-restricted (checked through ``/sapi/v1/account/apiRestrictions``).
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import time
from decimal import Decimal
from typing import Any, Mapping
from urllib.parse import urlencode

import httpx

from services.bybit_client import (
    BybitAmbiguousOrderError,
    BybitCredentials,
    BybitError,
    BybitPermissionError,
    InstrumentRules,
)

LIVE_FAPI = "https://fapi.binance.com"
LIVE_SAPI = "https://api.binance.com"


class BinanceError(BybitError):
    pass


class BinancePermissionError(BybitPermissionError):
    pass


class BinanceAmbiguousOrderError(BybitAmbiguousOrderError):
    pass


_STATUS = {"NEW": "New", "PARTIALLY_FILLED": "PartiallyFilled", "FILLED": "Filled", "CANCELED": "Cancelled",
           "REJECTED": "Rejected", "EXPIRED": "Deactivated", "EXPIRED_IN_MATCH": "Deactivated"}


def demo_base_url() -> str:
    return (os.getenv("BINANCE_FUTURES_DEMO_URL") or "https://demo-fapi.binance.com").rstrip("/")


class BinanceUsdmClient:
    provider = "binance"

    def __init__(
        self,
        credentials: BybitCredentials,
        *,
        timeout_seconds: float = 10.0,
        recv_window_ms: int = 5000,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.credentials = credentials
        self.timeout_seconds = max(2.0, min(float(timeout_seconds), 30.0))
        self.recv_window_ms = max(1000, min(int(recv_window_ms), 10000))
        self.base_url = demo_base_url() if credentials.testnet else LIVE_FAPI
        self._client = client

    # ------------------------------------------------------------------ transport
    def _sign(self, params: Mapping[str, Any]) -> tuple[str, dict[str, str]]:
        key = self.credentials.api_key.strip()
        secret = self.credentials.api_secret.strip()
        if not key or not secret:
            raise BinanceError("missing_credentials")
        query = urlencode([(k, v) for k, v in params.items() if v is not None])
        signature = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        return f"{query}&signature={signature}", {"X-MBX-APIKEY": key}

    async def _request(self, method: str, path: str, *, params: Mapping[str, Any] | None = None,
                       signed: bool = True, base: str | None = None) -> Any:
        method = method.upper()
        clean = {k: (format(v, "f") if isinstance(v, Decimal) else v) for k, v in dict(params or {}).items()
                 if v is not None}
        headers: dict[str, str] = {}
        if signed:
            clean["recvWindow"] = self.recv_window_ms
            clean["timestamp"] = int(time.time() * 1000)
            query, headers = self._sign(clean)
        else:
            query = urlencode(list(clean.items()))
        url = f"{base or self.base_url}{path}" + (f"?{query}" if query else "")
        owns = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            response = await client.request(method, url, headers=headers)
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise BinanceError(f"transport:{type(exc).__name__}") from exc
        finally:
            if owns:
                await client.aclose()
        if response.status_code >= 400 or (isinstance(payload, dict) and int(payload.get("code", 0) or 0) < 0):
            code = payload.get("code") if isinstance(payload, dict) else response.status_code
            message = str(payload.get("msg") if isinstance(payload, dict) else "provider_rejected")[:160]
            raise BinanceError(f"provider:{code}:{message}")
        return payload

    # ------------------------------------------------------------------ permissions
    @staticmethod
    def validate_trade_only_permissions(info: Mapping[str, Any]) -> dict[str, Any]:
        if bool(info.get("enableWithdrawals")):
            raise BinancePermissionError("binance_withdraw_permission_present")
        if bool(info.get("enableInternalTransfer")) or bool(info.get("permitsUniversalTransfer")):
            raise BinancePermissionError("binance_transfer_permission_present")
        if not bool(info.get("enableFutures")):
            raise BinancePermissionError("binance_futures_permission_missing")
        return {"read_only": False, "trade": True, "withdraw": False, "internal_transfer": False,
                "ip_bound": bool(info.get("ipRestrict")), "permissions": sorted(k for k, v in info.items() if v is True)}

    async def verify_trade_only_key(self, *, require_ip_binding: bool = True) -> dict[str, Any]:
        if self.credentials.testnet:
            # Demo keys cannot withdraw and have no /sapi restrictions endpoint;
            # a signed account read proves the key trades futures.
            await self._request("GET", "/fapi/v2/account")
            return {"read_only": False, "trade": True, "withdraw": False, "internal_transfer": False,
                    "ip_bound": True, "permissions": ["futures_demo"]}
        info = await self._request("GET", "/sapi/v1/account/apiRestrictions", base=LIVE_SAPI)
        result = self.validate_trade_only_permissions(dict(info or {}))
        if require_ip_binding and not result["ip_bound"]:
            raise BinancePermissionError("binance_api_key_ip_binding_required")
        return result

    # ------------------------------------------------------------------ account and market
    async def get_wallet_balance(self, *, coin: str | None = None) -> dict[str, Any]:
        account = dict(await self._request("GET", "/fapi/v2/account") or {})
        return {"list": [{
            "totalEquity": account.get("totalMarginBalance"),
            "totalWalletBalance": account.get("totalWalletBalance"),
            "totalAvailableBalance": account.get("availableBalance"),
            "accountType": "USDM_FUTURES",
        }]}

    async def get_instrument_rules(self, symbol: str, *, category: str = "linear") -> InstrumentRules:
        info = dict(await self._request("GET", "/fapi/v1/exchangeInfo", signed=False) or {})
        row = next((s for s in info.get("symbols") or [] if str(s.get("symbol")).upper() == symbol.upper()), None)
        if not row or str(row.get("status") or "TRADING") != "TRADING":
            raise BinanceError("instrument_not_found")
        filters = {f.get("filterType"): f for f in row.get("filters") or []}
        lot = filters.get("MARKET_LOT_SIZE") or filters.get("LOT_SIZE") or {}
        price = filters.get("PRICE_FILTER") or {}
        notional = filters.get("MIN_NOTIONAL") or {}
        max_qty = lot.get("maxQty")
        return InstrumentRules(
            symbol=str(row.get("symbol")).upper(), category=category,
            tick_size=Decimal(str(price.get("tickSize") or "0")),
            qty_step=Decimal(str(lot.get("stepSize") or "0")),
            min_qty=Decimal(str(lot.get("minQty") or "0")),
            max_qty=Decimal(str(max_qty)) if max_qty else None,
            min_notional=Decimal(str(notional.get("notional"))) if notional.get("notional") else None,
        )

    async def get_ticker(self, symbol: str, *, category: str = "linear") -> dict[str, Any]:
        data = dict(await self._request("GET", "/fapi/v1/ticker/price", params={"symbol": symbol.upper()},
                                        signed=False) or {})
        if not data.get("price"):
            raise BinanceError("ticker_not_found")
        return {"symbol": data.get("symbol"), "lastPrice": data.get("price"), "_provider_time_ms": data.get("time")}

    async def get_positions(self, *, symbol: str, category: str = "linear") -> list[dict[str, Any]]:
        rows = await self._request("GET", "/fapi/v2/positionRisk", params={"symbol": symbol.upper()})
        out = []
        for row in rows or []:
            amount = Decimal(str(row.get("positionAmt") or "0"))
            out.append({
                "symbol": row.get("symbol"), "size": str(abs(amount)),
                "side": "Buy" if amount > 0 else "Sell" if amount < 0 else "",
                "avgPrice": row.get("entryPrice"), "markPrice": row.get("markPrice"),
                "unrealisedPnl": row.get("unRealizedProfit"), "leverage": row.get("leverage"),
            })
        return out

    async def get_order(self, *, symbol: str, category: str = "linear", order_id: str | None = None,
                        order_link_id: str | None = None) -> dict[str, Any] | None:
        try:
            row = dict(await self._request("GET", "/fapi/v1/order", params={
                "symbol": symbol.upper(), "orderId": order_id or None,
                "origClientOrderId": None if order_id else order_link_id}) or {})
        except BinanceError as exc:
            if ":-2013:" in str(exc):  # order does not exist (yet)
                return None
            raise
        return {**row, "orderId": str(row.get("orderId") or ""), "orderLinkId": row.get("clientOrderId"),
                "orderStatus": _STATUS.get(str(row.get("status") or ""), str(row.get("status") or "")),
                "cumExecQty": row.get("executedQty"), "avgPrice": row.get("avgPrice")}

    async def get_closed_pnl(self, *, symbol: str, start_time_ms: int | None = None, end_time_ms: int | None = None,
                             category: str = "linear", limit: int = 50) -> list[dict[str, Any]]:
        rows = await self._request("GET", "/fapi/v1/income", params={
            "symbol": symbol.upper(), "incomeType": "REALIZED_PNL", "startTime": start_time_ms,
            "endTime": end_time_ms, "limit": max(1, min(int(limit), 1000))})
        return [{"symbol": r.get("symbol"), "closedPnl": r.get("income"), "updatedTime": r.get("time"),
                 "createdTime": r.get("time"), "orderId": str(r.get("tradeId") or "")} for r in rows or []]

    # ------------------------------------------------------------------ orders
    async def _protect(self, symbol: str, close_side: str, kind: str, trigger: Decimal, link_id: str) -> dict:
        return dict(await self._request("POST", "/fapi/v1/algoOrder", params={
            "algoType": "CONDITIONAL", "symbol": symbol, "side": close_side, "type": kind,
            "triggerPrice": format(trigger, "f"), "closePosition": "true", "workingType": "MARK_PRICE",
            "priceProtect": "true", "clientAlgoId": f"{link_id[:30]}-{'sl' if kind == 'STOP_MARKET' else 'tp'}",
        }) or {})

    async def _emergency_close(self, symbol: str, close_side: str, qty: Decimal) -> None:
        try:
            await self._request("POST", "/fapi/v1/order", params={
                "symbol": symbol, "side": close_side, "type": "MARKET", "quantity": format(qty, "f"),
                "reduceOnly": "true"})
        finally:
            try:
                await self._request("DELETE", "/fapi/v1/algoOpenOrders", params={"symbol": symbol})
            except BinanceError:
                pass

    async def place_market_order(self, *, symbol: str, side: str, qty: Decimal, stop_loss: Decimal,
                                 take_profit: Decimal, order_link_id: str, category: str = "linear") -> dict[str, Any]:
        rules = await self.get_instrument_rules(symbol)
        normalized_qty = rules.quantize_qty(Decimal(qty))
        normalized_sl = rules.quantize_price(Decimal(stop_loss))
        normalized_tp = rules.quantize_price(Decimal(take_profit))
        ticker = await self.get_ticker(rules.symbol)
        reference = Decimal(str(ticker.get("lastPrice") or "0"))
        if reference <= 0:
            raise BinanceError("invalid_reference_price")
        if rules.min_notional is not None and normalized_qty * reference < rules.min_notional:
            raise BinanceError("order_notional_below_minimum")
        is_buy = str(side).lower() in {"buy", "long"}
        if (is_buy and not (normalized_sl < reference < normalized_tp)) or (
                not is_buy and not (normalized_tp < reference < normalized_sl)):
            raise BinanceError("protective_levels_on_wrong_side_of_price")
        link_id = str(order_link_id or "").strip()[:36]
        if not link_id:
            raise BinanceError("order_link_id_required")
        open_side, close_side = ("BUY", "SELL") if is_buy else ("SELL", "BUY")
        try:
            ack = dict(await self._request("POST", "/fapi/v1/order", params={
                "symbol": rules.symbol, "side": open_side, "type": "MARKET", "quantity": format(normalized_qty, "f"),
                "newClientOrderId": link_id, "newOrderRespType": "RESULT"}) or {})
        except BinanceError as exc:
            if str(exc).startswith("transport:"):
                raise BinanceAmbiguousOrderError(str(exc)) from exc
            raise
        order_id = str(ack.get("orderId") or "").strip()
        if not order_id:
            raise BinanceAmbiguousOrderError("order_ack_missing_order_id")
        confirmed = None
        attempts = max(1, min(int(os.getenv("BINANCE_ORDER_CONFIRM_ATTEMPTS", "5") or 5), 10))
        for attempt in range(attempts):
            try:
                confirmed = await self.get_order(symbol=rules.symbol, order_id=order_id)
            except BinanceError as exc:
                raise BinanceAmbiguousOrderError(f"order_confirmation_{exc}") from exc
            if confirmed is not None and confirmed.get("orderStatus") in {"Filled", "Rejected", "Cancelled",
                                                                          "Deactivated"}:
                break
            await asyncio.sleep(0.25 * (attempt + 1))
        if confirmed is None:
            raise BinanceAmbiguousOrderError("order_ack_not_confirmed")
        status = str(confirmed.get("orderStatus") or "")
        if status in {"Rejected", "Cancelled", "Deactivated"}:
            raise BinanceError(f"order_{status.lower()}")
        filled = Decimal(str(confirmed.get("cumExecQty") or "0")) or normalized_qty
        try:
            stop = await self._protect(rules.symbol, close_side, "STOP_MARKET", normalized_sl, link_id)
            target = await self._protect(rules.symbol, close_side, "TAKE_PROFIT_MARKET", normalized_tp, link_id)
        except BinanceError as exc:
            await self._emergency_close(rules.symbol, close_side, filled)
            raise BinanceError(f"protective_order_failed_position_closed:{exc}") from exc
        return {
            "success": True, "order_id": order_id, "order_link_id": link_id, "status": status or "Accepted",
            "qty": format(normalized_qty, "f"), "symbol": rules.symbol, "provider": "binance",
            "stop_algo_id": str(stop.get("algoId") or ""), "take_profit_algo_id": str(target.get("algoId") or ""),
        }


__all__ = ["BinanceAmbiguousOrderError", "BinanceError", "BinancePermissionError", "BinanceUsdmClient"]
