"""Authenticated Bybit V5 client with trade-only permission enforcement.

The client treats an order-create acknowledgement as provisional and confirms
it through the authenticated order endpoint before returning success.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Any, Mapping
from urllib.parse import urlencode

import httpx


class BybitError(RuntimeError):
    pass


class BybitPermissionError(BybitError):
    pass


class BybitAmbiguousOrderError(BybitError):
    pass


@dataclass(frozen=True, slots=True)
class BybitCredentials:
    api_key: str
    api_secret: str
    testnet: bool = False


@dataclass(frozen=True, slots=True)
class InstrumentRules:
    symbol: str
    category: str
    tick_size: Decimal
    qty_step: Decimal
    min_qty: Decimal
    max_qty: Decimal | None = None
    min_notional: Decimal | None = None

    def quantize_qty(self, value: Decimal) -> Decimal:
        if self.qty_step <= 0:
            raise BybitError("invalid_qty_step")
        units = (value / self.qty_step).to_integral_value(rounding=ROUND_DOWN)
        qty = units * self.qty_step
        if qty < self.min_qty:
            raise BybitError("quantity_below_minimum")
        if self.max_qty is not None and qty > self.max_qty:
            raise BybitError("quantity_above_maximum")
        return qty

    def quantize_price(self, value: Decimal) -> Decimal:
        if self.tick_size <= 0:
            raise BybitError("invalid_tick_size")
        units = (value / self.tick_size).to_integral_value(rounding=ROUND_DOWN)
        return units * self.tick_size


class BybitV5Client:
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
        self.base_url = "https://api-testnet.bybit.com" if credentials.testnet else "https://api.bybit.com"
        self._client = client

    @staticmethod
    def _canonical_json(payload: Mapping[str, Any]) -> str:
        return json.dumps(dict(payload), separators=(",", ":"), ensure_ascii=False)

    def _headers(self, *, timestamp_ms: int, payload_text: str) -> dict[str, str]:
        key = self.credentials.api_key.strip()
        secret = self.credentials.api_secret.strip()
        if not key or not secret:
            raise BybitError("missing_credentials")
        material = f"{timestamp_ms}{key}{self.recv_window_ms}{payload_text}"
        signature = hmac.new(secret.encode(), material.encode(), hashlib.sha256).hexdigest()
        return {
            "X-BAPI-API-KEY": key,
            "X-BAPI-TIMESTAMP": str(timestamp_ms),
            "X-BAPI-SIGN": signature,
            "X-BAPI-RECV-WINDOW": str(self.recv_window_ms),
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        method = method.upper()
        clean_params = {k: v for k, v in dict(params or {}).items() if v is not None}
        query = urlencode(sorted((str(k), str(v)) for k, v in clean_params.items()))
        body_text = self._canonical_json(body or {}) if method != "GET" else ""
        payload_text = query if method == "GET" else body_text
        headers: dict[str, str] = {}
        if authenticated:
            headers = self._headers(timestamp_ms=int(time.time() * 1000), payload_text=payload_text)

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                params=clean_params if method == "GET" else None,
                content=body_text if method != "GET" else None,
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise BybitError(f"transport:{type(exc).__name__}") from exc
        finally:
            if owns_client:
                await client.aclose()
        if not isinstance(payload, dict):
            raise BybitError("invalid_response")
        ret_code = int(payload.get("retCode", -1))
        if ret_code != 0:
            message = str(payload.get("retMsg") or "provider_rejected")
            raise BybitError(f"provider:{ret_code}:{message[:160]}")
        return payload

    async def get_api_key_info(self) -> dict[str, Any]:
        payload = await self._request("GET", "/v5/user/query-api")
        return dict(payload.get("result") or {})

    @staticmethod
    def validate_trade_only_permissions(info: Mapping[str, Any]) -> dict[str, Any]:
        read_only = int(info.get("readOnly") or 0) == 1
        permissions = info.get("permissions") or {}
        flattened: set[str] = set()
        if isinstance(permissions, Mapping):
            for group, values in permissions.items():
                flattened.add(str(group).strip().lower())
                if isinstance(values, (list, tuple, set)):
                    flattened.update(str(value).strip().lower() for value in values)
                elif values is not None:
                    flattened.add(str(values).strip().lower())
        elif isinstance(permissions, (list, tuple, set)):
            flattened.update(str(value).strip().lower() for value in permissions)

        forbidden = {value for value in flattened if any(token in value for token in ("withdraw", "transfer", "submembertransfer"))}
        has_trade = any(
            token in value
            for value in flattened
            for token in ("order", "position", "spottrade", "contracttrade", "options")
        )
        if read_only:
            raise BybitPermissionError("bybit_api_key_is_read_only")
        if forbidden:
            raise BybitPermissionError("bybit_withdraw_or_transfer_permission_present")
        if not has_trade:
            raise BybitPermissionError("bybit_trade_permission_missing")
        return {
            "read_only": False,
            "trade": True,
            "withdraw": False,
            "internal_transfer": False,
            "ip_bound": bool(str(info.get("ips") or "").strip()),
            "permissions": sorted(flattened),
        }

    async def verify_trade_only_key(self, *, require_ip_binding: bool = True) -> dict[str, Any]:
        result = self.validate_trade_only_permissions(await self.get_api_key_info())
        if require_ip_binding and not result["ip_bound"]:
            raise BybitPermissionError("bybit_api_key_ip_binding_required")
        return result

    async def get_wallet_balance(self, *, coin: str | None = None) -> dict[str, Any]:
        params = {"accountType": "UNIFIED", "coin": coin.upper() if coin else None}
        payload = await self._request("GET", "/v5/account/wallet-balance", params=params)
        return dict(payload.get("result") or {})

    async def get_instrument_rules(self, symbol: str, *, category: str = "linear") -> InstrumentRules:
        payload = await self._request(
            "GET", "/v5/market/instruments-info",
            params={"category": category, "symbol": symbol.upper()},
            authenticated=False,
        )
        rows = list((payload.get("result") or {}).get("list") or [])
        if not rows:
            raise BybitError("instrument_not_found")
        row = dict(rows[0])
        price_filter = dict(row.get("priceFilter") or {})
        lot_filter = dict(row.get("lotSizeFilter") or {})
        max_qty_raw = lot_filter.get("maxOrderQty") or lot_filter.get("maxMktOrderQty")
        min_notional_raw = lot_filter.get("minNotionalValue")
        return InstrumentRules(
            symbol=str(row.get("symbol") or symbol).upper(),
            category=category,
            tick_size=Decimal(str(price_filter.get("tickSize") or "0")),
            qty_step=Decimal(str(lot_filter.get("qtyStep") or "0")),
            min_qty=Decimal(str(lot_filter.get("minOrderQty") or "0")),
            max_qty=Decimal(str(max_qty_raw)) if max_qty_raw else None,
            min_notional=Decimal(str(min_notional_raw)) if min_notional_raw else None,
        )

    async def get_ticker(self, symbol: str, *, category: str = "linear") -> dict[str, Any]:
        payload = await self._request(
            "GET", "/v5/market/tickers",
            params={"category": category, "symbol": symbol.upper()},
            authenticated=False,
        )
        rows = list((payload.get("result") or {}).get("list") or [])
        if not rows:
            raise BybitError("ticker_not_found")
        return dict(rows[0])

    async def get_order(
        self,
        *,
        symbol: str,
        category: str = "linear",
        order_id: str | None = None,
        order_link_id: str | None = None,
    ) -> dict[str, Any] | None:
        payload = await self._request(
            "GET", "/v5/order/realtime",
            params={
                "category": category,
                "symbol": symbol.upper(),
                "orderId": order_id,
                "orderLinkId": order_link_id,
            },
        )
        rows = list((payload.get("result") or {}).get("list") or [])
        return dict(rows[0]) if rows else None

    async def get_positions(self, *, symbol: str, category: str = "linear") -> list[dict[str, Any]]:
        payload = await self._request(
            "GET", "/v5/position/list",
            params={"category": category, "symbol": symbol.upper()},
        )
        return [dict(item) for item in list((payload.get("result") or {}).get("list") or [])]

    async def get_closed_pnl(
        self,
        *,
        symbol: str,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        category: str = "linear",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET", "/v5/position/closed-pnl",
            params={
                "category": category,
                "symbol": symbol.upper(),
                "startTime": start_time_ms,
                "endTime": end_time_ms,
                "limit": max(1, min(int(limit), 100)),
            },
        )
        return [dict(item) for item in list((payload.get("result") or {}).get("list") or [])]

    async def place_market_order(
        self,
        *,
        symbol: str,
        side: str,
        qty: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal,
        order_link_id: str,
        category: str = "linear",
    ) -> dict[str, Any]:
        rules = await self.get_instrument_rules(symbol, category=category)
        normalized_qty = rules.quantize_qty(Decimal(qty))
        normalized_sl = rules.quantize_price(Decimal(stop_loss))
        normalized_tp = rules.quantize_price(Decimal(take_profit))
        ticker = await self.get_ticker(rules.symbol, category=category)
        reference_price = Decimal(str(ticker.get("lastPrice") or "0"))
        if reference_price <= 0:
            raise BybitError("invalid_reference_price")
        if rules.min_notional is not None and normalized_qty * reference_price < rules.min_notional:
            raise BybitError("order_notional_below_minimum")
        link_id = str(order_link_id or "").strip()[:36]
        if not link_id:
            raise BybitError("order_link_id_required")
        body = {
            "category": category,
            "symbol": rules.symbol,
            "side": "Buy" if str(side).lower() in {"buy", "long"} else "Sell",
            "orderType": "Market",
            "qty": format(normalized_qty, "f"),
            "timeInForce": "IOC",
            "stopLoss": format(normalized_sl, "f"),
            "takeProfit": format(normalized_tp, "f"),
            "tpslMode": "Full",
            "orderLinkId": link_id,
        }
        try:
            payload = await self._request("POST", "/v5/order/create", body=body)
        except BybitError as exc:
            # A transport failure after the request leaves the client may still
            # mean Bybit accepted the order.  Never treat that as a definite
            # rejection or release the execution quota for an automatic retry.
            if str(exc).startswith("transport:"):
                raise BybitAmbiguousOrderError(str(exc)) from exc
            raise
        result = dict(payload.get("result") or {})
        order_id = str(result.get("orderId") or "").strip()
        if not order_id:
            raise BybitAmbiguousOrderError("order_ack_missing_order_id")
        confirmed = None
        attempts = max(1, min(int(os.getenv("BYBIT_ORDER_CONFIRM_ATTEMPTS", "5") or 5), 10))
        base_delay = max(0.05, min(float(os.getenv("BYBIT_ORDER_CONFIRM_DELAY_SECONDS", "0.25") or 0.25), 2.0))
        for attempt in range(attempts):
            try:
                confirmed = await self.get_order(
                    symbol=rules.symbol,
                    category=category,
                    order_id=order_id,
                    order_link_id=link_id,
                )
            except BybitError as exc:
                raise BybitAmbiguousOrderError(f"order_confirmation_{exc}") from exc
            if confirmed is not None:
                break
            if attempt < attempts - 1:
                await asyncio.sleep(base_delay * (attempt + 1))
        if confirmed is None:
            raise BybitAmbiguousOrderError("order_ack_not_confirmed")
        status = str(confirmed.get("orderStatus") or "").strip()
        if status in {"Rejected", "Cancelled", "Deactivated"}:
            raise BybitError(f"order_{status.lower()}")
        return {
            "success": True,
            "order_id": order_id,
            "order_link_id": link_id,
            "status": status or "Accepted",
            "qty": format(normalized_qty, "f"),
            "symbol": rules.symbol,
            "provider": "bybit",
        }


__all__ = [
    "BybitAmbiguousOrderError",
    "BybitCredentials",
    "BybitError",
    "BybitPermissionError",
    "BybitV5Client",
    "InstrumentRules",
]
