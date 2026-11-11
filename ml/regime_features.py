"""Regime and context features (feature schema v6, 11 Nov 2026).

Research basis: the system's own outcomes (the same setup lost on crypto 5m and won
on crypto 1h; chop/ADX/confluence rejections won on crypto 1h only) and the
meta-labelling literature for crypto/FX (Lopez de Prado; Kaufman's efficiency
ratio as a trend/chop measure; volatility regime and intraday seasonality as
standard context). The model had no timeframe or chop information at all.

* ``timeframe_enc``: 5m=1, 15m=2, 30m=3, 1h=4, 4h=5, 1d=6 (0 unknown);
* ``efficiency_ratio_20``: |close[-1]-close[-21]| / sum(|close diffs|), 0-1;
* ``range_to_atr_20``: (max high - min low over 20 bars) / ATR14, clamped 0-20;
* ``volatility_ratio_5_20``: mean true range of the last 5 bars / of the last 20,
  clamped 0-5 (contraction < 1 < expansion);
* ``hour_sin`` / ``hour_cos``: UTC hour of the signal on the unit circle;
* ``is_weekend``: Saturday/Sunday UTC (crypto trades through the weekend).

Every value uses closed bars only: training reads ``market_candles`` with the
same availability rule as the other candle features; live scoring passes the
closed candles it already has. Missing data gives 0.0.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

FEATURES = ("timeframe_enc", "efficiency_ratio_20", "range_to_atr_20", "volatility_ratio_5_20",
            "hour_sin", "hour_cos", "is_weekend")
TIMEFRAME_CODES = {"5m": 1, "15m": 2, "30m": 3, "1h": 4, "4h": 5, "1d": 6}


def _true_ranges(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> list[float]:
    out = []
    for i in range(1, min(len(highs), len(lows), len(closes))):
        h, l, pc = float(highs[i]), float(lows[i]), float(closes[i - 1])
        out.append(max(h - l, abs(h - pc), abs(l - pc)))
    return out


def candle_features(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> dict[str, float]:
    out = {"efficiency_ratio_20": 0.0, "range_to_atr_20": 0.0, "volatility_ratio_5_20": 0.0}
    n = min(len(highs), len(lows), len(closes))
    if n < 22:
        return out
    closes, highs, lows = list(closes)[-n:], list(highs)[-n:], list(lows)[-n:]
    window = closes[-21:]
    path = sum(abs(window[i] - window[i - 1]) for i in range(1, len(window)))
    if path > 0:
        out["efficiency_ratio_20"] = round(abs(window[-1] - window[0]) / path, 6)
    trs = _true_ranges(highs, lows, closes)
    atr14 = sum(trs[-14:]) / 14.0 if len(trs) >= 14 else 0.0
    if atr14 > 0:
        span = max(highs[-20:]) - min(lows[-20:])
        out["range_to_atr_20"] = round(max(0.0, min(20.0, span / atr14)), 6)
    if len(trs) >= 20:
        recent, base = sum(trs[-5:]) / 5.0, sum(trs[-20:]) / 20.0
        if base > 0:
            out["volatility_ratio_5_20"] = round(max(0.0, min(5.0, recent / base)), 6)
    return out


def context_features(timeframe: Any, when: datetime | None) -> dict[str, float]:
    tf = str(timeframe or "").strip().lower()
    out = {"timeframe_enc": float(TIMEFRAME_CODES.get(tf, 0)), "hour_sin": 0.0, "hour_cos": 0.0, "is_weekend": 0.0}
    if when is not None:
        stamp = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
        stamp = stamp.astimezone(timezone.utc)
        hour = stamp.hour + stamp.minute / 60.0
        out["hour_sin"] = round(math.sin(2 * math.pi * hour / 24.0), 6)
        out["hour_cos"] = round(math.cos(2 * math.pi * hour / 24.0), 6)
        out["is_weekend"] = 1.0 if stamp.weekday() >= 5 else 0.0
    return out


def live_values(signal: dict[str, Any], candles: Iterable[dict[str, Any]]) -> dict[str, float]:
    rows = [c for c in candles if isinstance(c, dict)]
    highs = [float(c.get("high") or 0.0) for c in rows]
    lows = [float(c.get("low") or 0.0) for c in rows]
    closes = [float(c.get("close") or 0.0) for c in rows]
    return {**candle_features(highs, lows, closes),
            **context_features(signal.get("timeframe"), datetime.now(timezone.utc))}


async def fill_frame(frame: Any, *, session_factory: Any = None, bars: int = 80) -> Any:
    """Set the v6 columns on a training frame, point in time per row (closed bars only)."""
    import bisect

    import pandas as pd

    stamps = pd.to_datetime(frame["created_at"], errors="coerce", utc=True)
    for column in FEATURES:
        frame[column] = 0.0
    context = [context_features(tf, (None if pd.isna(ts) else ts.to_pydatetime()))
               for tf, ts in zip(frame.get("timeframe", [""] * len(frame)), stamps)]
    for column in ("timeframe_enc", "hour_sin", "hour_cos", "is_weekend"):
        frame[column] = [row[column] for row in context]
    if session_factory is None or "asset" not in frame.columns:
        return frame

    from sqlalchemy import text

    from ml.train_model import _candle_availability_times

    series: dict[tuple[str, str], list[int]] = {}
    for index, (asset, tf) in enumerate(zip(frame["asset"].astype(str), frame["timeframe"].astype(str))):
        series.setdefault((asset, tf.lower()), []).append(index)
    values = {column: list(frame[column]) for column in ("efficiency_ratio_20", "range_to_atr_20",
                                                         "volatility_ratio_5_20")}
    for (asset, tf), indexes in series.items():
        valid = [stamps.iloc[i] for i in indexes if not pd.isna(stamps.iloc[i])]
        if not valid:
            continue
        seconds = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}.get(tf, 3600)
        lo = int(min(valid).timestamp() * 1000) - (bars + 2) * seconds * 1000
        hi = int(max(valid).timestamp() * 1000)
        try:
            async with session_factory() as session:
                rows = (await session.execute(text(
                    "SELECT open_time_ms, close_time_ms, high, low, close FROM market_candles "
                    "WHERE symbol=:a AND timeframe=:tf AND open_time_ms BETWEEN :lo AND :hi ORDER BY open_time_ms"),
                    {"a": asset, "tf": tf, "lo": lo, "hi": hi})).all()
                await session.rollback()
        except Exception:
            continue
        if not rows:
            continue
        available = _candle_availability_times([int(r[0]) for r in rows], [r[1] for r in rows], seconds)
        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]
        closes = [float(r[4]) for r in rows]
        for i in indexes:
            if pd.isna(stamps.iloc[i]):
                continue
            stop = bisect.bisect_right(available, int(stamps.iloc[i].timestamp() * 1000))
            start = max(0, stop - bars)
            feats = candle_features(highs[start:stop], lows[start:stop], closes[start:stop])
            for column, value in feats.items():
                values[column][i] = value
    for column, column_values in values.items():
        frame[column] = column_values
    return frame
