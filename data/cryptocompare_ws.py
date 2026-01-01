from __future__ import annotations

import asyncio
import json
import os
import random
from typing import Any, AsyncIterator, Iterable

import websockets


CC_WS_BASE = "wss://streamer.cryptocompare.com/v2?api_key="


def _env_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or str(default)).strip())
    except Exception:
        return int(default)


def _parse_symbol(symbol: str) -> tuple[str, str] | None:
    """Parse BTCUSDT -> (BTC, USDT)."""
    s = (symbol or "").upper().strip().replace("/", "").replace("-", "")
    if len(s) < 6:
        return None
    for q in ("USDT", "USDC", "BUSD", "USD"):
        if s.endswith(q) and len(s) > len(q):
            return s[: -len(q)], q
    return None


def build_subs(symbols: Iterable[str]) -> list[str]:
    """Build CryptoCompare 'subs' strings.

    We subscribe to:
    - TYPE=5: CCCAGG current aggregate (ticker-ish)
    - TYPE=0: CCCAGG trades (for volume/time and candle building)

    Note: CryptoCompare WS is best-effort; when trades are sparse we still build
    OHLC from ticker updates.
    """

    subs: list[str] = []
    for sym in symbols:
        parsed = _parse_symbol(sym)
        if not parsed:
            continue
        fsym, tsym = parsed
        subs.append(f"5~CCCAGG~{fsym}~{tsym}")
        subs.append(f"0~CCCAGG~{fsym}~{tsym}")

    # Bound number of subs to avoid CC limits.
    max_subs = _env_int("CRYPTOCOMPARE_WS_MAX_SUBS", 200)
    return subs[: max(1, int(max_subs))]


async def iter_events(*, symbols: list[str]) -> AsyncIterator[dict[str, Any]]:
    """Yield normalized events from CryptoCompare WS.

    Events:
+    - {"type": "tick", "symbol": "BTCUSDT", "price": 123.4, "event_time_ms": 1700000000000}
+    - {"type": "trade", "symbol": "BTCUSDT", "price": 123.4, "volume": 0.01, "event_time_ms": ...}

    CryptoCompare payload formats vary by subscription TYPE; we parse the common
    fields defensively.
    """

    api_key = (os.getenv("CRYPTOCOMPARE_API_KEY") or "").strip()
    url = CC_WS_BASE + api_key

    subs = build_subs(symbols)
    if not subs:
        return

    backoff = 1.0
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20, close_timeout=10) as ws:
                backoff = 1.0

                await ws.send(json.dumps({"action": "SubAdd", "subs": subs}))

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue

                    # Heartbeats / control messages
                    if not isinstance(msg, dict):
                        continue
                    if msg.get("TYPE") == "429" or msg.get("TYPE") == 429:
                        # Rate limited
                        await asyncio.sleep(5)
                        continue

                    # CCCAGG current aggregate (TYPE=5)
                    try:
                        msg_type = str(msg.get("TYPE") or "")
                    except Exception:
                        msg_type = ""

                    if msg_type == "5":
                        fsym = str(msg.get("FROMSYMBOL") or "").upper().strip()
                        tsym = str(msg.get("TOSYMBOL") or "").upper().strip()
                        if not fsym or not tsym:
                            continue
                        sym = f"{fsym}{tsym}"
                        try:
                            price = float(msg.get("PRICE"))
                        except Exception:
                            continue
                        try:
                            ts = int(msg.get("LASTUPDATE") or msg.get("TS") or 0)
                        except Exception:
                            ts = 0
                        et_ms = int(ts) * 1000 if ts else None
                        yield {"type": "tick", "symbol": sym, "price": price, "event_time_ms": et_ms}
                        continue

                    # CCCAGG trade (TYPE=0)
                    if msg_type == "0":
                        fsym = str(msg.get("FROMSYMBOL") or "").upper().strip()
                        tsym = str(msg.get("TOSYMBOL") or "").upper().strip()
                        if not fsym or not tsym:
                            continue
                        sym = f"{fsym}{tsym}"
                        try:
                            price = float(msg.get("PRICE"))
                        except Exception:
                            continue
                        # Trade volume can show up as QUANTITY or LASTVOLUME depending on stream.
                        vol = 0.0
                        for k in ("QUANTITY", "LASTVOLUME", "VOLUME"):
                            try:
                                if msg.get(k) is not None:
                                    vol = float(msg.get(k) or 0.0)
                                    break
                            except Exception:
                                continue
                        try:
                            ts = int(msg.get("TS") or msg.get("LASTUPDATE") or 0)
                        except Exception:
                            ts = 0
                        et_ms = int(ts) * 1000 if ts else None
                        yield {"type": "trade", "symbol": sym, "price": price, "volume": vol, "event_time_ms": et_ms}
                        continue
        except Exception:
            await asyncio.sleep(backoff + random.random())
            backoff = min(60.0, backoff * 2.0)
