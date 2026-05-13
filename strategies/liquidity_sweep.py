from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np


@dataclass(slots=True, frozen=True)
class _SweepConfig:
    min_candles: int = 40
    fvg_lookback: int = 5
    sweep_window: int = 5
    rr_ratio: float = 3.0
    atr_multiplier: float = 0.5


def _env_bool(name: str, default: bool = False) -> bool:
    import os

    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _is_fx(symbol: str) -> bool:
    s = str(symbol or "").upper().strip()
    return len(s) == 6 and s.isalpha()


def _is_crypto(symbol: str) -> bool:
    s = str(symbol or "").upper().strip()
    return s.endswith(("USDT", "BUSD", "USDC", "BTC", "ETH"))


def _is_commodity(symbol: str) -> bool:
    s = str(symbol or "").upper().strip()
    return s in {"XAUUSD", "XAGUSD", "WTI", "BRENT", "CL=F", "GC=F", "SI=F"}


def _session_allowed_for_fx() -> bool:
    if not _env_bool("LS_FX_SESSION_FILTER_ENABLED", True):
        return True
    allowed_raw = str(os.getenv("LS_FX_ALLOWED_SESSIONS") or "london,newyork,overlap").strip().lower()
    allowed = {x.strip() for x in allowed_raw.split(",") if x.strip()}
    utc_hour = int(datetime.utcnow().hour)
    checks = {
        "london": 7 <= utc_hour < 16,
        "newyork": 13 <= utc_hour < 22,
        "ny": 13 <= utc_hour < 22,
        "overlap": 13 <= utc_hour < 17,
    }
    return any(checks.get(item, False) for item in allowed)


def _to_arrays(candles: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    opens = np.asarray([float(c.get("open") or 0.0) for c in candles], dtype=float)
    highs = np.asarray([float(c.get("high") or 0.0) for c in candles], dtype=float)
    lows = np.asarray([float(c.get("low") or 0.0) for c in candles], dtype=float)
    closes = np.asarray([float(c.get("close") or 0.0) for c in candles], dtype=float)
    volumes = np.asarray([float(c.get("volume") or 0.0) for c in candles], dtype=float)
    return opens, highs, lows, closes, volumes


def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0.0
    prev_close = closes[:-1]
    tr = np.maximum(highs[1:] - lows[1:], np.maximum(np.abs(highs[1:] - prev_close), np.abs(lows[1:] - prev_close)))
    tail = tr[-period:] if len(tr) >= period else tr
    return float(tail.mean()) if tail.size else 0.0


def _select_htf_candles(market_data: dict[str, Any]) -> list[dict[str, Any]]:
    for tf in ("1d", "4h"):
        tf_data = market_data.get(tf)
        if isinstance(tf_data, dict):
            candles = tf_data.get("candles") or []
            if len(candles) >= 10:
                return list(candles)
    return []


def _select_exec_timeframe(market_data: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    for tf in ("1m", "5m"):
        tf_data = market_data.get(tf)
        if isinstance(tf_data, dict):
            candles = tf_data.get("candles") or []
            if len(candles) >= 20:
                return tf, tf_data
    return None, None


def _previous_session_high_low(highs: np.ndarray, lows: np.ndarray) -> tuple[float, float]:
    if len(highs) < 5 or len(lows) < 5:
        return 0.0, 0.0
    return float(np.max(highs[:-1])), float(np.min(lows[:-1]))


def _detect_bullish_signal(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, atr_val: float) -> dict[str, float] | None:
    if len(closes) < 8:
        return None
    pdh, pdl = _previous_session_high_low(highs[-24:], lows[-24:])
    recent_lows = lows[-6:-1] if len(lows) >= 6 else lows[:-1]
    recent_highs = highs[-6:-1] if len(highs) >= 6 else highs[:-1]
    if recent_lows.size == 0 or recent_highs.size == 0:
        return None
    swept = float(np.min(recent_lows)) < pdl and float(closes[-1]) > pdl
    mss = float(closes[-1]) > float(np.max(recent_highs))
    c1_high = float(highs[-3])
    c2_low = float(lows[-2])
    c2_high = float(highs[-2])
    c3_low = float(lows[-1])
    fvg = c3_low > c1_high
    impulse_ok = (c2_high - c2_low) > (atr_val * 1.5)
    if swept and mss and fvg and impulse_ok:
        gap_low = c1_high
        gap_high = c3_low
        entry = (gap_low + gap_high) / 2.0
        stop = float(np.min(recent_lows)) - (atr_val * _SweepConfig.atr_multiplier)
        return {
            "pdh": pdh,
            "pdl": pdl,
            "entry": entry,
            "stop": stop,
            "gap_low": gap_low,
            "gap_high": gap_high,
            "mss_level": float(np.max(recent_highs)),
            "sweep_level": float(np.min(recent_lows)),
        }
    return None


def _detect_bearish_signal(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, atr_val: float) -> dict[str, float] | None:
    if len(closes) < 8:
        return None
    pdh, pdl = _previous_session_high_low(highs[-24:], lows[-24:])
    recent_highs = highs[-6:-1] if len(highs) >= 6 else highs[:-1]
    recent_lows = lows[-6:-1] if len(lows) >= 6 else lows[:-1]
    if recent_highs.size == 0 or recent_lows.size == 0:
        return None
    swept = float(np.max(recent_highs)) > pdh and float(closes[-1]) < pdh
    mss = float(closes[-1]) < float(np.min(recent_lows))
    c1_low = float(lows[-3])
    c2_high = float(highs[-2])
    c2_low = float(lows[-2])
    c3_high = float(highs[-1])
    fvg = c3_high < c1_low
    impulse_ok = (c2_high - c2_low) > (atr_val * 1.5)
    if swept and mss and fvg and impulse_ok:
        gap_high = c1_low
        gap_low = c3_high
        entry = (gap_low + gap_high) / 2.0
        stop = float(np.max(recent_highs)) + (atr_val * _SweepConfig.atr_multiplier)
        return {
            "pdh": pdh,
            "pdl": pdl,
            "entry": entry,
            "stop": stop,
            "gap_low": gap_low,
            "gap_high": gap_high,
            "mss_level": float(np.min(recent_lows)),
            "sweep_level": float(np.max(recent_highs)),
        }
    return None


def detect_liquidity_sweep_fvg(df_1m: list[dict[str, Any]], df_htf: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect an institutional liquidity sweep + FVG pattern.

    This function is intentionally stateless and vectorized over the supplied
    candle arrays. It returns zero or one setup for each direction.
    """
    cfg = _SweepConfig()
    if not df_1m or not df_htf:
        return []

    _, highs, lows, closes, volumes = _to_arrays(df_1m)
    _, htf_highs, htf_lows, htf_closes, _ = _to_arrays(df_htf)
    if len(closes) < cfg.min_candles or len(htf_closes) < 10:
        return []

    atr_val = _atr(highs, lows, closes)
    if atr_val <= 0:
        return []

    bullish = _detect_bullish_signal(highs, lows, closes, atr_val)
    bearish = _detect_bearish_signal(highs, lows, closes, atr_val)
    results: list[dict[str, Any]] = []

    if bullish is not None:
        results.append({
            "direction": "LONG",
            "entry": float(bullish["entry"]),
            "stop_loss": float(bullish["stop"]),
            "take_profit": float(bullish["entry"] + (abs(bullish["entry"] - bullish["stop"]) * cfg.rr_ratio)),
            "confidence": 0.88,
            "rr_ratio": cfg.rr_ratio,
            "sweep_level": float(bullish["sweep_level"]),
            "mss_level": float(bullish["mss_level"]),
            "fvg_low": float(bullish["gap_low"]),
            "fvg_high": float(bullish["gap_high"]),
        })

    if bearish is not None:
        results.append({
            "direction": "SHORT",
            "entry": float(bearish["entry"]),
            "stop_loss": float(bearish["stop"]),
            "take_profit": float(bearish["entry"] - (abs(bearish["entry"] - bearish["stop"]) * cfg.rr_ratio)),
            "confidence": 0.88,
            "rr_ratio": cfg.rr_ratio,
            "sweep_level": float(bearish["sweep_level"]),
            "mss_level": float(bearish["mss_level"]),
            "fvg_low": float(bearish["gap_low"]),
            "fvg_high": float(bearish["gap_high"]),
        })

    return results


def liquidity_sweep_strategies(asset: str, market_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Public strategy wrapper used by the orchestrator."""
    try:
        symbol = str(asset or "").upper().strip()
        if _is_fx(symbol) and not _session_allowed_for_fx():
            return []

        exec_tf, exec_data = _select_exec_timeframe(market_data)
        htf_candles = _select_htf_candles(market_data)
        if not exec_tf or exec_data is None or not htf_candles:
            return []

        candles = list(exec_data.get("candles") or [])
        if len(candles) < 20:
            return []

        _, highs, lows, closes, volumes = _to_arrays(candles)
        atr_val = _atr(highs, lows, closes)
        if atr_val <= 0:
            return []

        base_signals = detect_liquidity_sweep_fvg(candles, htf_candles)
        out: list[dict[str, Any]] = []
        for sig in base_signals:
            sig.update({
                "asset": symbol,
                "symbol": symbol,
                "timeframe": exec_tf,
                "strategy_name": "Liquidity Sweep FVG",
                "strategy_group": "liquidity",
                "reasoning": (
                    f"Sweep + MSS + FVG detected on {exec_tf}; entry in gap, stop below sweep, RR 1:{_SweepConfig.rr_ratio:.1f}."
                ),
                "strength": float(sig.get("confidence") or 0.0),
                "volatility": float(atr_val / max(1e-9, float(closes[-1]))),
                "market_open_confirmed": True,
                "rr_ratio": _SweepConfig.rr_ratio,
                "created_at": datetime.utcnow(),
                "source": "liquidity_sweep",
            })
            out.append(sig)
        return out
    except Exception as exc:
        logging.getLogger(__name__).exception("Liquidity sweep strategy failed: %s", exc)
        return []
