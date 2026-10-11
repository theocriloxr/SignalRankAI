"""Optional read-only SDK adapters in the canonical candle waterfall.

SDK packages load in an isolated interpreter. Importing this module opens no
connections and does not load optional dependencies in application services.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from data.sdk_gateway import read_sdk
from market_data_sdk.worker import CCXT_VENUES, INTERVALS


def crypto_pair(symbol: str) -> str | None:
    """Preserve the requested quote currency; never substitute USD for USDT."""
    value = str(symbol or "").strip().upper().replace("-", "/").replace("_", "/")
    if "/" not in value:
        for quote in ("USDT", "USDC", "USD", "EUR", "GBP", "BTC", "ETH"):
            if value.endswith(quote) and len(value) > len(quote):
                value = f"{value[:-len(quote)]}/{quote}"
                break
    return value if re.fullmatch(r"[A-Z0-9]{2,12}/[A-Z0-9]{2,8}", value) else None


def _bars(operation: str, symbol: str, timeframe: str, limit: int, timeout: float,
          **payload: Any) -> list[dict[str, Any]]:
    if timeframe not in INTERVALS or type(limit) is not int or not 1 <= limit <= 1000:
        return []
    rows = read_sdk(operation, dict(symbol=symbol, timeframe=timeframe, limit=limit, **payload), timeout=timeout)
    return rows if isinstance(rows, list) else []


def marketdata_get_candles(symbol: str, timeframe: str, limit: int = 200,
                           timeout: float = 10.0) -> list[dict[str, Any]]:
    value = str(symbol or "").strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.]{0,14}", value) or not os.getenv("MARKETDATA_TOKEN", "").strip():
        return []
    mode = os.getenv("MARKETDATA_MODE", "live").strip().lower()
    if mode not in {"live", "cached", "delayed"}:
        return []
    return _bars("marketdata_bars", value, timeframe, limit, timeout, mode=mode)


def ccxt_get_candles(symbol: str, timeframe: str, limit: int = 200,
                     timeout: float = 10.0) -> list[dict[str, Any]]:
    pair = crypto_pair(symbol)
    venue = os.getenv("CCXT_MARKET_DATA_EXCHANGE", "").strip().lower()
    if not pair or venue not in CCXT_VENUES:
        return []
    return _bars("ccxt_bars", pair, timeframe, limit, timeout, venue=venue)


def ibkr_get_candles(symbol: str, timeframe: str, limit: int = 200,
                     timeout: float = 10.0) -> list[dict[str, Any]]:
    # Contract mappings are explicit operator configuration, never inferred
    # futures/options proxies for a cash index or a spot commodity.
    try:
        contracts = json.loads(os.getenv("IBKR_MARKET_DATA_CONTRACTS_JSON", "{}"))
        contract = contracts.get(str(symbol or "").strip().upper())
        host = os.getenv("IBKR_MARKET_DATA_HOST", "").strip()
        port = int(os.getenv("IBKR_MARKET_DATA_PORT", "0"))
        client_id = int(os.getenv("IBKR_MARKET_DATA_CLIENT_ID", "71"))
        if not host or not isinstance(contract, dict) or not 1 <= port <= 65535 or not 1 <= client_id <= 2**31-1:
            return []
        from services.asset_mapper import classify_asset
        required_type = {"stock": "STK", "equity": "STK", "fx": "CASH", "forex": "CASH",
                         "index": "IND", "commodity": "CMDTY"}.get(str(classify_asset(symbol)).lower())
        if required_type is None or contract.get("secType") != required_type:
            return []
        if required_type == "CASH":
            compact = str(symbol).upper().replace("/", "")
            if compact != str(contract.get("symbol", "")) + str(contract.get("currency", "")):
                return []
        if required_type == "STK" and contract.get("symbol") != str(symbol).upper():
            return []
    except (ValueError, TypeError, AttributeError):
        return []
    return _bars("ibkr_bars", str(symbol).upper(), timeframe, limit, timeout,
                 host=host, port=port, client_id=client_id, contract=contract)


def coinbase_stream_quote(symbol: str, timeout: float = 5.0) -> dict[str, Any] | None:
    pair = crypto_pair(symbol)
    if not pair:
        return None
    result = read_sdk("coinbase_quote", {"symbol": pair.replace("/", "-")}, timeout=timeout)
    return result if isinstance(result, dict) else None
