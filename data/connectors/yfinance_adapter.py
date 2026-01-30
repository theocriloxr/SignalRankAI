from __future__ import annotations

from typing import List, Dict, Any

try:
    import yfinance as yf
except Exception:  # pragma: no cover - optional dependency
    yf = None


def _normalize_symbol(symbol: str) -> str:
    # Common mapping: BTCUSDT -> BTC-USD, ETHUSDT -> ETH-USD
    s = symbol.strip()
    if s.upper().endswith("USDT"):
        base = s[:-4]
        return f"{base}-USD"
    if len(s) >= 4 and s[-3:] == "USD" and "-" not in s:
        return s[:-3] + "-USD"
    return s


def get_candles(symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Fetch candles via yfinance as a best-effort adapter.

    Returns a list of dicts: {time, open, high, low, close, volume} or
    an empty list on failure. This adapter is intentionally lightweight
    and used as a fallback provider.
    """
    if yf is None:
        raise RuntimeError("yfinance not installed")

    symbol_norm = _normalize_symbol(symbol)
    # yfinance intervals: "1m","2m","5m","15m","30m","60m","90m","1h","1d","1wk","1mo"
    interval = timeframe
    # choose a conservative history period to cover typical limits
    period = "60d" if "d" in timeframe or "h" in timeframe else "7d"

    try:
        t = yf.Ticker(symbol_norm)
        df = t.history(period=period, interval=interval)
        if df is None or df.empty:
            return []
        out: List[Dict[str, Any]] = []
        for idx, row in df.iterrows():
            try:
                out.append(
                    {
                        "time": idx,
                        "open": float(row.get("Open", 0.0)),
                        "high": float(row.get("High", 0.0)),
                        "low": float(row.get("Low", 0.0)),
                        "close": float(row.get("Close", 0.0)),
                        "volume": float(row.get("Volume", 0.0)),
                    }
                )
            except Exception:
                # skip malformed rows
                continue
        return out[-limit:]
    except Exception:
        return []
