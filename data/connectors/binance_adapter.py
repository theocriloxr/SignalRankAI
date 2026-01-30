from __future__ import annotations

from typing import List, Dict, Any
import requests
import logging

logger = logging.getLogger(__name__)


def get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Simple Binance REST adapter for klines.

    Returns list of {timestamp, open, high, low, close, volume} or empty list.
    """
    tf_map = {"5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}
    interval = tf_map.get((timeframe or "").strip(), "1h")
    sym = (symbol or "").upper().strip().replace("/", "").replace("-", "")
    if sym.endswith("USD") and not sym.endswith("USDT"):
        sym = sym[:-3] + "USDT"
    if not sym or len(sym) < 6:
        return []

    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": sym, "interval": interval, "limit": limit}
    try:
        resp = requests.get(url, params=params, timeout=10)
        if not resp.ok:
            logger.debug("binance_adapter HTTP %s %s", resp.status_code, resp.text[:200])
            return []
        payload = resp.json()
        if not isinstance(payload, list):
            return []
        out: List[Dict[str, Any]] = []
        for row in payload:
            try:
                out.append(
                    {
                        "timestamp": int(row[0]),
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume": float(row[5]),
                    }
                )
            except Exception:
                continue
        return out
    except Exception:
        return []
