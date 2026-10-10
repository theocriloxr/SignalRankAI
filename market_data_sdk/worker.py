"""Isolated market-data SDK worker; intentionally imports only stdlib at startup.

Run by data.sdk_gateway, never with broker order instructions. The worker has no
application database, Telegram token, execution keys or application imports.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import json
import logging
import math
import os
import re
import sys
import threading
import time
from typing import Any

INTERVALS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}
CCXT_VENUES = frozenset({"coinbase", "kraken", "okx", "bybit", "binance", "kucoin"})


def normalize_bars(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    result: dict[float, dict[str, Any]] = {}
    for row in rows:
        raw = row["timestamp"]
        if isinstance(raw, datetime):
            if raw.tzinfo is None:
                raise ValueError("ambiguous_bar_timezone")
            stamp = raw.timestamp()
        elif isinstance(raw, str) and not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", raw):
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("ambiguous_bar_timezone")
            stamp = parsed.timestamp()
        else:
            stamp = float(raw)
        if not math.isfinite(stamp) or stamp <= 0:
            raise ValueError("invalid_sdk_bar_timestamp")
        while stamp > 10_000_000_000:
            stamp /= 1000
        values = [float(row[key]) for key in ("open", "high", "low", "close", "volume")]
        if not math.isfinite(stamp) or stamp <= 0 or not all(math.isfinite(x) for x in values):
            raise ValueError("invalid_sdk_bar")
        o, h, low, c, volume = values
        if min(o, h, low, c) <= 0 or volume < 0 or not low <= min(o, c) <= max(o, c) <= h:
            raise ValueError("invalid_sdk_bar_geometry")
        normalized = dict(timestamp=int(stamp * 1000), open=o, high=h, low=low, close=c, volume=volume)
        if stamp in result and result[stamp] != normalized:
            raise ValueError("conflicting_sdk_bars")
        result[stamp] = normalized
    return [result[key] for key in sorted(result)][-limit:]


def _bar_request(payload: dict[str, Any]) -> tuple[str, str, int]:
    symbol = str(payload.get("symbol") or "").upper().strip()
    timeframe = str(payload.get("timeframe") or "").lower()
    count = payload.get("limit", 200)
    if not re.fullmatch(r"[A-Z0-9./:_-]{1,60}", symbol) or timeframe not in INTERVALS:
        raise ValueError("invalid_sdk_instrument_or_interval")
    if type(count) is not int or not 1 <= count <= 1000:
        raise ValueError("invalid_sdk_bar_limit")
    return symbol, timeframe, count


def alpaca_bars(payload: dict[str, Any], timeout: float) -> list[dict[str, Any]]:
    from alpaca.common.enums import Sort
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
    from alpaca.data.models import BarSet
    from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    symbol, tf, count = _bar_request(payload)
    unit = TimeFrameUnit("Day" if tf == "1d" else "Hour" if tf in {"1h", "4h"} else "Min")
    amount = 1 if tf == "1d" else INTERVALS[tf] // (3600 if tf in {"1h", "4h"} else 60)
    timeframe = TimeFrame(amount, unit)
    key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
    secret = os.getenv("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise ValueError("alpaca_credentials_missing")
    crypto = payload.get("crypto") is True
    client = (CryptoHistoricalDataClient if crypto else StockHistoricalDataClient)(key, secret)
    client._retry = 0
    end = datetime.now(timezone.utc)
    kwargs: dict[str, Any] = dict(symbol_or_symbols=symbol, timeframe=timeframe, limit=count,
                  start=end-timedelta(seconds=INTERVALS[tf]*(count+20)*7), end=end, sort=Sort.DESC)
    try:
        if isinstance(client, CryptoHistoricalDataClient):
            result = client.get_crypto_bars(CryptoBarsRequest(**kwargs))
        else:
            kwargs.update(feed=DataFeed(str(payload.get("feed") or "iex")), adjustment="raw")
            result = client.get_stock_bars(StockBarsRequest(**kwargs))
        if not isinstance(result, BarSet):
            raise ValueError("alpaca_response_not_bar_set")
        bars = result.data.get(symbol, [])
        return normalize_bars([dict(timestamp=b.timestamp, open=b.open, high=b.high, low=b.low,
                                    close=b.close, volume=b.volume) for b in bars], count)
    finally:
        client._session.close()


def marketdata_bars(payload: dict[str, Any], timeout: float) -> list[dict[str, Any]]:
    from marketdata import MarketDataClient, Mode, OutputFormat

    symbol, tf, count = _bar_request(payload)
    token = os.getenv("MARKETDATA_TOKEN")
    if not token:
        raise ValueError("marketdata_credentials_missing")
    resolution = "D" if tf == "1d" else str(INTERVALS[tf] // 60)
    mode = str(payload.get("mode") or "live")
    if mode not in {"live", "cached", "delayed"}:
        raise ValueError("marketdata_mode_invalid")
    # The SDK constructor fetches account limits. The process deadline bounds
    # that request too; the installed SDK has no constructor timeout option.
    client = MarketDataClient(token=token, max_retries=0)
    try:
        bars = client.stocks.candles(symbol, resolution=resolution, countback=count,
                                    adjust_splits=False, mode=Mode(mode), output_format=OutputFormat.INTERNAL)
        if not isinstance(bars, list):
            raise ValueError("marketdata_request_not_successful")
        return normalize_bars([dict(timestamp=b.t, open=b.o, high=b.h, low=b.l, close=b.c, volume=b.v)
                               for b in bars], count)
    finally:
        client.client.close()


def ccxt_bars(payload: dict[str, Any], timeout: float) -> list[dict[str, Any]]:
    import ccxt

    symbol, tf, count = _bar_request(payload)
    venue = str(payload.get("venue") or "")
    if venue not in CCXT_VENUES or "/" not in symbol or ":" in symbol:
        raise ValueError("unsupported_ccxt_spot_market")
    # No API keys, user-controlled URLs, sandbox override or trading methods.
    exchange = getattr(ccxt, venue)({"enableRateLimit": True, "timeout": max(1, int(timeout*1000)),
                                   "options": {"defaultType": "spot"}})
    try:
        exchange.load_markets()
        market = exchange.markets.get(symbol)
        if not market or market.get("spot") is not True or market.get("active") is False:
            raise ValueError("ccxt_spot_market_unavailable")
        if not exchange.has.get("fetchOHLCV") or tf not in (exchange.timeframes or {}):
            raise ValueError("ccxt_interval_unavailable")
        bars = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=count)
        return normalize_bars([dict(zip(("timestamp", "open", "high", "low", "close", "volume"), b))
                               for b in bars], count)
    finally:
        close = getattr(exchange, "close", None)
        if callable(close):
            close()


def ibkr_bars(payload: dict[str, Any], timeout: float) -> list[dict[str, Any]]:
    from ibapi.client import EClient
    from ibapi.contract import Contract
    from ibapi.wrapper import EWrapper

    _, tf, count = _bar_request(payload)
    specification = payload.get("contract")
    if not isinstance(specification, dict):
        raise ValueError("ibkr_contract_required")
    allowed = {"conId", "symbol", "secType", "exchange", "primaryExchange", "currency", "localSymbol"}
    if set(specification) - allowed:
        raise ValueError("ibkr_contract_field_not_allowed")
    if specification.get("secType") not in {"STK", "CASH", "IND", "FUT", "OPT", "CMDTY"}:
        raise ValueError("ibkr_contract_type_not_supported")
    if specification.get("secType") not in {"STK", "CASH"} and not specification.get("conId"):
        raise ValueError("ibkr_qualified_contract_id_required")
    if not specification.get("exchange") or not specification.get("currency"):
        raise ValueError("ibkr_contract_venue_and_currency_required")
    for key, value in specification.items():
        if key == "conId":
            if type(value) is not int or value <= 0:
                raise ValueError("invalid_ibkr_contract_id")
        elif not isinstance(value, str) or not re.fullmatch(r"[A-Z0-9. /_-]{1,60}", value):
            raise ValueError("invalid_ibkr_contract_field")
    contract = Contract()
    for key, value in specification.items():
        setattr(contract, key, value)
    ready, finished, realtime = threading.Event(), threading.Event(), threading.Event()
    rows: list[dict[str, Any]] = []
    errors: list[int] = []

    class Reader(EWrapper, EClient):
        def __init__(self):
            EWrapper.__init__(self)
            EClient.__init__(self, self)

        def nextValidId(self, orderId):
            ready.set()

        def marketDataType(self, reqId, marketDataType):
            if reqId == 1002:
                if marketDataType != 1:
                    errors.append(-2)
                realtime.set()

        def historicalData(self, reqId, bar):
            if reqId != 1001:
                return
            stamp = str(bar.date)
            if re.fullmatch(r"[0-9]{8}", stamp):
                stamp = datetime.strptime(stamp, "%Y%m%d").replace(tzinfo=timezone.utc)
            # MIDPOINT series have no traded volume. Keep that distinction on
            # each candle rather than presenting zero as measured volume.
            midpoint = contract.secType in {"CASH", "IND", "CMDTY"}
            volume = float(bar.volume)
            if volume < 0 and not midpoint:
                errors.append(-1)
                finished.set()
                return
            rows.append(dict(timestamp=stamp, open=bar.open, high=bar.high, low=bar.low,
                             close=bar.close, volume=0.0 if midpoint else volume))
            if len(rows) > 10000:
                errors.append(-1)
                finished.set()

        def historicalDataEnd(self, reqId, start, end):
            if reqId == 1001:
                finished.set()

        def error(self, reqId, *args):
            # Older/newer official clients differ by an error timestamp argument.
            code = args[1] if len(args) >= 3 and isinstance(args[1], int) else args[0] if args else -1
            if code not in {2104, 2106, 2107, 2108, 2158}:
                errors.append(int(code))
                finished.set()

    reader = Reader()
    thread = None
    deadline = time.monotonic()+timeout
    try:
        reader.connect(str(payload["host"]), int(payload["port"]), clientId=int(payload["client_id"]))
        thread = threading.Thread(target=reader.run, daemon=True)
        thread.start()
        if not ready.wait(max(0, deadline-time.monotonic())):
            raise TimeoutError("ibkr_connection_not_ready")
        reader.reqMarketDataType(1)  # Never request frozen/delayed substitution.
        reader.reqMktData(1002, contract, "", False, False, [])
        if not realtime.wait(max(0, deadline-time.monotonic())) or errors:
            raise ValueError("ibkr_realtime_entitlement_not_confirmed")
        reader.cancelMktData(1002)
        sizes = {"1m": "1 min", "5m": "5 mins", "15m": "15 mins", "30m": "30 mins",
                 "1h": "1 hour", "4h": "4 hours", "1d": "1 day"}
        days = max(1, min(365, math.ceil(INTERVALS[tf]*(count+20)*7/86400)))
        duration = f"{days} D"
        source = "MIDPOINT" if contract.secType in {"CASH", "IND", "CMDTY"} else "TRADES"
        reader.reqHistoricalData(1001, contract, "", duration, sizes[tf], source, 1, 2, False, [])
        if not finished.wait(max(0, deadline-time.monotonic())) or errors:
            raise ValueError("ibkr_history_unavailable")
        normalized = normalize_bars(rows, count)
        if source == "MIDPOINT":
            for row in normalized:
                row.update(price_type="midpoint", volume_available=False)
        return normalized
    finally:
        if reader.isConnected():
            reader.cancelHistoricalData(1001)
            reader.cancelMktData(1002)
        reader.disconnect()
        if thread:
            thread.join(timeout=0.5)


def coinbase_quote(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    from websocket import create_connection

    symbol = str(payload.get("symbol") or "").upper()
    if not re.fullmatch(r"[A-Z0-9]{2,12}-[A-Z0-9]{2,8}", symbol):
        raise ValueError("invalid_coinbase_product")
    deadline = time.monotonic()+timeout
    ws = create_connection("wss://ws-feed.exchange.coinbase.com", timeout=timeout, enable_multithread=True)
    try:
        ws.send(json.dumps({"type": "subscribe", "product_ids": [symbol], "channels": ["ticker"]}))
        for _ in range(50):
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                break
            ws.settimeout(remaining)
            item = json.loads(ws.recv())
            if item.get("type") != "ticker" or item.get("product_id") != symbol:
                continue
            bid, ask, price = (float(item[key]) for key in ("best_bid", "best_ask", "price"))
            stamp = datetime.fromisoformat(item["time"].replace("Z", "+00:00")).timestamp()
            if not all(math.isfinite(x) and x > 0 for x in (bid, ask, price, stamp)) or bid > ask:
                raise ValueError("invalid_stream_quote")
            if not -5 <= time.time()-stamp <= 30:
                raise ValueError("stale_or_future_stream_quote")
            return dict(symbol=symbol, bid=bid, ask=ask, last=price, timestamp=stamp,
                        provider="coinbase_websocket", sequence=item.get("sequence"))
        raise TimeoutError("stream_quote_not_received")
    finally:
        ws.close()


OPERATIONS = {"alpaca_bars": alpaca_bars, "marketdata_bars": marketdata_bars, "ccxt_bars": ccxt_bars,
              "ibkr_bars": ibkr_bars, "coinbase_quote": coinbase_quote}


def main() -> int:
    logging.disable(logging.CRITICAL)
    try:
        request = json.loads(sys.stdin.read(65537))
        operation = str(request["operation"])
        seconds = float(request["timeout"])
        if operation not in OPERATIONS or not math.isfinite(seconds) or not 0 < seconds <= 30:
            raise ValueError("invalid_sdk_request")
        # Third-party libraries must never add text or request details to the
        # normalized response channel. Their stdout and logs are suppressed.
        with open(os.devnull, "w", encoding="utf-8") as sink, redirect_stdout(sink):
            data = OPERATIONS[operation](dict(request["payload"]), seconds)
        response = {"ok": True, "data": data}
    except Exception as exc:
        response = {"ok": False, "error": type(exc).__name__}
    sys.stdout.write(json.dumps(response, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
