from __future__ import annotations

import asyncio
import json
import os
import random
from typing import Any, AsyncIterator, Iterable

import websockets


BINANCE_STREAM_BASE = "wss://stream.binance.com:9443/stream?streams="


def _env_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or str(default)).strip())
    except Exception:
        return int(default)


def _tf_to_binance_interval(tf: str) -> str | None:
    tf = (tf or "").strip().lower()
    if tf in {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"}:
        return tf
    return None


def build_streams(symbols: Iterable[str], *, intervals: Iterable[str]) -> list[str]:
    out: list[str] = []
    for s in symbols:
        sym = str(s or "").lower().strip()
        if not sym:
            continue
        out.append(f"{sym}@ticker")
        for tf in intervals:
            i = _tf_to_binance_interval(tf)
            if not i:
                continue
            out.append(f"{sym}@kline_{i}")
    # Binance limits stream count; keep it bounded.
    max_streams = _env_int("BINANCE_WS_MAX_STREAMS", 200)
    return out[: max(1, int(max_streams))]


async def iter_events(
    *,
    symbols: list[str],
    intervals: list[str],
) -> AsyncIterator[dict[str, Any]]:
    """Yield normalized WS events.

    Events:
    - {"type": "tick", "symbol": "BTCUSDT", "price": 123.4, "event_time_ms": 1700000000000}
    - {"type": "kline", "symbol": "BTCUSDT", "timeframe": "1m", "open_time_ms": ..., ...}

    Notes:
    - This is best-effort and reconnects automatically.
    - If Binance is geo-blocked in your Railway region, this will fail; caller should treat it as optional.
    """

    streams = build_streams(symbols, intervals=intervals)
    if not streams:
        return

    url = BINANCE_STREAM_BASE + "/".join(streams)
    backoff = 1.0
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20, close_timeout=10) as ws:
                backoff = 1.0
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue

                    data = msg.get("data") if isinstance(msg, dict) else None
                    if not isinstance(data, dict):
                        continue

                    # Ticker
                    if data.get("e") == "24hrTicker":
                        sym = str(data.get("s") or "").upper().strip()
                        try:
                            price = float(data.get("c"))
                        except Exception:
                            continue
                        try:
                            et = int(data.get("E"))
                        except Exception:
                            et = None
                        yield {"type": "tick", "symbol": sym, "price": price, "event_time_ms": et}
                        continue

                    # Kline
                    if data.get("e") == "kline":
                        k = data.get("k")
                        if not isinstance(k, dict):
                            continue
                        sym = str(k.get("s") or data.get("s") or "").upper().strip()
                        tf = str(k.get("i") or "").lower().strip()
                        try:
                            ot = int(k.get("t"))
                            ct = int(k.get("T"))
                            o = float(k.get("o"))
                            h = float(k.get("h"))
                            l = float(k.get("l"))
                            c = float(k.get("c"))
                            v = float(k.get("v") or 0.0)
                            is_final = bool(k.get("x"))
                        except Exception:
                            continue
                        yield {
                            "type": "kline",
                            "symbol": sym,
                            "timeframe": tf,
                            "open_time_ms": ot,
                            "close_time_ms": ct,
                            "open": o,
                            "high": h,
                            "low": l,
                            "close": c,
                            "volume": v,
                            "is_final": is_final,
                        }
                        continue
        except Exception:
            # Reconnect with jittered exponential backoff.
            await asyncio.sleep(backoff + random.random())
            backoff = min(60.0, backoff * 2.0)
