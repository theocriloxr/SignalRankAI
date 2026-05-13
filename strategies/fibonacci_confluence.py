from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
from engine.signal_analytics import calculate_volume_delta
import os
import logging


@dataclass(slots=True, frozen=True)
class _FibConfig:
    lookback: int = 80
    pivot_window: int = 2
    fib_level: float = 0.618
    rr_ratio: float = 3.0
    atr_tolerance_mult: float = 0.35


def _to_arrays(candles: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    opens = np.asarray([float(c.get("open") or 0.0) for c in candles], dtype=float)
    highs = np.asarray([float(c.get("high") or 0.0) for c in candles], dtype=float)
    lows = np.asarray([float(c.get("low") or 0.0) for c in candles], dtype=float)
    closes = np.asarray([float(c.get("close") or 0.0) for c in candles], dtype=float)
    volumes = np.asarray([float(c.get("volume") or 0.0) for c in candles], dtype=float)
    return opens, highs, lows, closes, volumes


def _ema(values: np.ndarray, period: int) -> float:
    if values.size < period or period <= 1:
        return float(values[-1]) if values.size else 0.0
    alpha = 2.0 / (period + 1.0)
    ema = float(np.mean(values[:period]))
    for v in values[period:]:
        ema = (float(v) * alpha) + (ema * (1.0 - alpha))
    return float(ema)


def _rsi_series(closes: np.ndarray, period: int = 14) -> np.ndarray:
    if closes.size < period + 1:
        return np.asarray([], dtype=float)
    deltas = np.diff(closes)
    gains = np.clip(deltas, 0.0, None)
    losses = np.clip(-deltas, 0.0, None)
    avg_gain = np.convolve(gains, np.ones(period) / period, mode="valid")
    avg_loss = np.convolve(losses, np.ones(period) / period, mode="valid")
    rs = np.divide(avg_gain, np.maximum(avg_loss, 1e-9))
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.astype(float)


def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    if closes.size < period + 1:
        return 0.0
    prev_close = closes[:-1]
    tr = np.maximum(highs[1:] - lows[1:], np.maximum(np.abs(highs[1:] - prev_close), np.abs(lows[1:] - prev_close)))
    tail = tr[-period:] if tr.size >= period else tr
    return float(tail.mean()) if tail.size else 0.0


def _pivot_mask(values: np.ndarray, window: int = 2, mode: str = "low") -> np.ndarray:
    if values.size < (window * 2) + 1:
        return np.zeros_like(values, dtype=bool)
    center = values[window:-window]
    if mode == "low":
        left = np.vstack([values[i: i + center.size] for i in range(window)])
        right = np.vstack([values[i + window + 1: i + window + 1 + center.size] for i in range(window)])
        mask = (center <= left.min(axis=0)) & (center <= right.min(axis=0))
    else:
        left = np.vstack([values[i: i + center.size] for i in range(window)])
        right = np.vstack([values[i + window + 1: i + window + 1 + center.size] for i in range(window)])
        mask = (center >= left.max(axis=0)) & (center >= right.max(axis=0))
    out = np.zeros_like(values, dtype=bool)
    out[window:-window] = mask
    return out


def _last_two_indices(mask: np.ndarray) -> list[int]:
    idx = np.flatnonzero(mask)
    if idx.size < 2:
        return []
    return [int(idx[-2]), int(idx[-1])]


def _nearest_zone(price: float, level: float, atr: float, is_long: bool) -> bool:
    tolerance = max(atr * _FibConfig.atr_tolerance_mult, abs(price) * 0.0015)
    return abs(price - level) <= tolerance if is_long else abs(price - level) <= tolerance


def _bias_from_htf(market_data: dict[str, Any]) -> tuple[str | None, float, float]:
    for tf in ("1d", "4h"):
        tf_data = market_data.get(tf)
        if not isinstance(tf_data, dict):
            continue
        ind = tf_data.get("indicators") or {}
        candles = tf_data.get("candles") or []
        if len(candles) < 30:
            continue
        closes = np.asarray([float(c.get("close") or 0.0) for c in candles], dtype=float)
        ema200 = float(ind.get("ema_200") or ind.get("ema200") or 0.0)
        if ema200 <= 0:
            ema200 = _ema(closes, 200)
        last = float(closes[-1])
        if last > ema200:
            return "LONG", last, ema200
        if last < ema200:
            return "SHORT", last, ema200
    return None, 0.0, 0.0


def _find_exec_tf(market_data: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    for tf in ("5m", "15m", "1h"):
        tf_data = market_data.get(tf)
        if isinstance(tf_data, dict) and len(tf_data.get("candles") or []) >= 40:
            return tf, tf_data
    return None, None


def fibonacci_confluence_strategies(asset: str, market_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Triple confluence at the 0.618 retracement with RSI divergence and a fresh zone.

    The strategy works on the execution timeframe (5m/15m/1h) while using
    4h/1d for directional bias.
    """
    try:
        cfg = _FibConfig()
        symbol = str(asset or "").upper().strip()
        exec_tf, tf_data = _find_exec_tf(market_data)
        if not exec_tf or not isinstance(tf_data, dict):
            return []

        candles = list(tf_data.get("candles") or [])
        if len(candles) < cfg.lookback:
            return []

        _, highs, lows, closes, volumes = _to_arrays(candles[-cfg.lookback:])
        if closes.size < cfg.lookback:
            return []

        atr_val = _atr(highs, lows, closes)
        if atr_val <= 0:
            return []

        bias, htf_close, htf_ema200 = _bias_from_htf(market_data)
        if bias is None:
            return []

        rsi = _rsi_series(closes)
        if rsi.size < 5:
            return []

        pivot_lows = _pivot_mask(lows, window=cfg.pivot_window, mode="low")
        pivot_highs = _pivot_mask(highs, window=cfg.pivot_window, mode="high")
        low_idx = _last_two_indices(pivot_lows)
        high_idx = _last_two_indices(pivot_highs)
        if not low_idx and not high_idx:
            return []

        swing_low = float(np.min(lows))
        swing_high = float(np.max(highs))
        if swing_high <= swing_low:
            return []

        # Golden Pocket zone: 0.618 - 0.786 retracement
        pocket_low_ratio = 0.618
        pocket_high_ratio = 0.786
        fib_long = swing_high - ((swing_high - swing_low) * pocket_low_ratio)
        fib_long_upper = swing_high - ((swing_high - swing_low) * pocket_high_ratio)
        fib_short = swing_low + ((swing_high - swing_low) * pocket_low_ratio)
        fib_short_upper = swing_low + ((swing_high - swing_low) * pocket_high_ratio)
        last_close = float(closes[-1])
        last_rsi = float(rsi[-1])
        rr = cfg.rr_ratio

        bullish_div = False
        bearish_div = False
        if low_idx:
            prev_i, last_i = low_idx
            price_lower_low = float(lows[last_i]) < float(lows[prev_i])
            rsi_higher_low = float(rsi[min(last_i - 1, rsi.size - 1)]) > float(rsi[min(prev_i - 1, rsi.size - 1)])
            bullish_div = price_lower_low and rsi_higher_low
        if high_idx:
            prev_i, last_i = high_idx
            price_higher_high = float(highs[last_i]) > float(highs[prev_i])
            rsi_lower_high = float(rsi[min(last_i - 1, rsi.size - 1)]) < float(rsi[min(prev_i - 1, rsi.size - 1)])
            bearish_div = price_higher_high and rsi_lower_high

        out: list[dict[str, Any]] = []
        fresh_demand = bool(low_idx) and abs(last_close - float(lows[low_idx[-1]])) <= max(atr_val * cfg.atr_tolerance_mult, last_close * 0.0015)
        fresh_supply = bool(high_idx) and abs(last_close - float(highs[high_idx[-1]])) <= max(atr_val * cfg.atr_tolerance_mult, last_close * 0.0015)

        # Tolerance buffer (e.g., 0.01% default) to count boundary touches as inside
        try:
            tol_pct = float((os.getenv("FIB_TOUCH_TOLERANCE_PCT") or "0.0001").strip())
        except Exception:
            tol_pct = 0.0001

        def _inside_zone(price: float, low: float, high: float) -> bool:
            if price >= min(low, high) and price <= max(low, high):
                return True
            # within tolerance of boundaries
            if abs(price - low) <= max(abs(price) * tol_pct, 1e-9):
                return True
            if abs(price - high) <= max(abs(price) * tol_pct, 1e-9):
                return True
            return False

        # Determine if trigger candle closes back inside Golden Pocket (5m strict)
        prev_close = float(closes[-2]) if closes.size >= 2 else float(closes[-1])
        last_close_price = float(last_close)

        long_zone_low = float(fib_long_upper)
        long_zone_high = float(fib_long)

        short_zone_low = float(fib_short)
        short_zone_high = float(fib_short_upper)

        # Check volume grading
        vol_stats = calculate_volume_delta(candles[-(cfg.lookback + 5):], window=20)
        rvol = float(vol_stats.get("rvol") or 0.0)

        if bias == "LONG" and bullish_div and fresh_demand and _inside_zone(last_close_price, long_zone_low, long_zone_high):
            # If running on 5m, require the candle to have closed back inside the pocket (prev outside -> last inside)
            if exec_tf == "5m":
                prev_outside = not _inside_zone(prev_close, long_zone_low, long_zone_high)
                if not prev_outside:
                    return []
            stop = swing_low - (atr_val * 0.5)
            risk = abs(last_close - stop)
            if risk > 0:
                sig = {
                    "asset": symbol,
                    "symbol": symbol,
                    "timeframe": exec_tf,
                    "direction": "LONG",
                    "entry": float((long_zone_low + long_zone_high) / 2.0),
                    "stop_loss": float(stop),
                    "take_profit": float(((long_zone_low + long_zone_high) / 2.0) + (risk * rr)),
                    "confidence": 0.86 + (0.06 if rvol >= 1.5 else 0.0),
                    "grade": ("A" if rvol >= 1.5 else "B"),
                    "rr_ratio": rr,
                    "strategy_name": "Fibonacci Confluence",
                    "strategy_group": "fibonacci",
                    "reasoning": (
                        "Golden Pocket (0.618-0.786) aligned with fresh demand, bullish RSI divergence, and HTF long bias."
                    ),
                    "swing_high": float(swing_high),
                    "swing_low": float(swing_low),
                    "fib_618": float((long_zone_low + long_zone_high) / 2.0),
                    "rsi_last": float(last_rsi),
                    "htf_bias_close": float(htf_close),
                    "htf_bias_ema200": float(htf_ema200),
                    "strength": 0.86 + (0.06 if rvol >= 1.5 else 0.0),
                    "market_open_confirmed": True,
                    "source": "fibonacci_confluence",
                    "created_at": datetime.utcnow(),
                }
                out.append(sig)

        if bias == "SHORT" and bearish_div and fresh_supply and _inside_zone(last_close_price, short_zone_low, short_zone_high):
            if exec_tf == "5m":
                prev_outside = not _inside_zone(prev_close, short_zone_low, short_zone_high)
                if not prev_outside:
                    return []
            stop = swing_high + (atr_val * 0.5)
            risk = abs(stop - last_close)
            if risk > 0:
                sig = {
                    "asset": symbol,
                    "symbol": symbol,
                    "timeframe": exec_tf,
                    "direction": "SHORT",
                    "entry": float((short_zone_low + short_zone_high) / 2.0),
                    "stop_loss": float(stop),
                    "take_profit": float(((short_zone_low + short_zone_high) / 2.0) - (risk * rr)),
                    "confidence": 0.86 + (0.06 if rvol >= 1.5 else 0.0),
                    "grade": ("A" if rvol >= 1.5 else "B"),
                    "rr_ratio": rr,
                    "strategy_name": "Fibonacci Confluence",
                    "strategy_group": "fibonacci",
                    "reasoning": (
                        "Golden Pocket (0.618-0.786) aligned with fresh supply, bearish RSI divergence, and HTF short bias."
                    ),
                    "swing_high": float(swing_high),
                    "swing_low": float(swing_low),
                    "fib_618": float((short_zone_low + short_zone_high) / 2.0),
                    "rsi_last": float(last_rsi),
                    "htf_bias_close": float(htf_close),
                    "htf_bias_ema200": float(htf_ema200),
                    "strength": 0.86 + (0.06 if rvol >= 1.5 else 0.0),
                    "market_open_confirmed": True,
                    "source": "fibonacci_confluence",
                    "created_at": datetime.utcnow(),
                }
                out.append(sig)

        return out
    except Exception:
        logging.getLogger(__name__).exception("Fibonacci confluence strategy failed")
        return []
