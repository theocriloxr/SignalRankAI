"""Strategies discovered from long price history (2 Nov 2026).

``ml/strategy_discovery.py`` searches a grid of rule families on years of
external price history for each asset and timeframe, keeps only rules that
survive walk-forward out-of-sample tests after costs, and publishes them as
*specs* to Redis. This module holds the parts shared by research and live
evaluation, so a rule is computed identically in the backtest and in the
engine:

- ``indicator_frame`` and ``entry_mask`` define each rule family;
- ``discovered_candidates`` runs the published specs on the engine's candles.

Modes (``DISCOVERED_STRATEGIES_MODE``):

- ``off``: nothing runs;
- ``shadow`` (default): matching specs are recorded as shadow observations in
  ``decision_log`` and followed forward by the shadow outcome tracker, so every
  discovered rule earns a live forward record (and feeds the per-asset
  strategy scorecard and ML training) without reaching any user;
- ``live``: specs whose forward record has been approved by the research loop
  are returned as normal candidates and pass through every engine gate (ML,
  risk, validation, expectancy). Unapproved specs stay in shadow.
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

REDIS_KEY = "discovered_strategies:v1"
GROUP = "discovered"

# family -> list of parameter dicts searched by research
FAMILY_GRID: dict[str, list[dict[str, Any]]] = {
    "trend_pullback": [
        {"fast": f, "slow": s, "rsi": r} for f, s in ((20, 50), (50, 100)) for r in (35, 40, 45)
    ],
    "donchian_breakout": [{"n": n, "adx": a} for n in (20, 55) for a in (0, 20, 25)],
    "bollinger_reversion": [{"k": k, "adx_max": a} for k in (2.0, 2.5) for a in (20, 25, 100)],
    "rsi_reversal": [{"level": lv, "trend": t} for lv in (25, 30) for t in (0, 1)],
    "squeeze_breakout": [{"q": q} for q in (0.1, 0.2)],
    "atr_momentum": [{"n": n, "k": k, "trend": t} for n in (10, 20) for k in (1.5, 2.5) for t in (0, 1)],
    "inside_bar_breakout": [{"trend": t} for t in (0, 1)],
    # Volume-confirmed families (skipped where the source has no real volume, e.g. spot forex).
    "volume_breakout": [{"n": n, "vz": z} for n in (20, 55) for z in (2.0, 3.0)],
    "obv_trend": [{"rsi": r} for r in (50, 55)],
    "vwap_reversion": [{"k": k, "adx_max": a} for k in (1.5, 2.5) for a in (25, 100)],
}
VOLUME_FAMILIES = frozenset({"volume_breakout", "obv_trend", "vwap_reversion"})

# Trading styles (services/trade_profiles.py): which timeframes each style is
# researched on, its stop/target pairs (stop in ATR, target in R) and its time stop
# in bars. A spec carries its style, so delivery can match the user's /profile.
STYLES: dict[str, dict[str, Any]] = {
    "scalp": {"timeframes": ("5m", "15m"), "exits": ((0.75, 1.0), (1.0, 1.0), (1.0, 1.5)),
              "hold": {"5m": 24, "15m": 16}},
    "day": {"timeframes": ("15m", "1h"), "exits": ((1.0, 1.5), (1.0, 2.0), (1.5, 2.0)),
            "hold": {"15m": 64, "1h": 24}},
    "swing": {"timeframes": ("4h", "1d"), "exits": ((1.0, 2.0), (1.5, 2.0), (1.5, 3.0), (2.0, 2.0)),
              "hold": {"4h": 30, "1d": 20}},
    "position": {"timeframes": ("1d",), "exits": ((2.0, 3.0), (2.5, 4.0), (3.0, 5.0)), "hold": {"1d": 60}},
    "flip": {"timeframes": ("15m", "1h", "4h"), "exits": ((0.8, 3.0), (1.0, 4.0), (1.0, 5.0)),
             "hold": {"15m": 96, "1h": 48, "4h": 24}},
}

EXIT_GRID: tuple[tuple[float, float], ...] = ((1.0, 1.5), (1.0, 2.0), (1.5, 2.0), (1.5, 3.0), (2.0, 2.0))
_TF_ALIASES = {"24h": "1d", "1day": "1d", "60m": "1h", "240m": "4h"}
MAX_HOLD_BARS = {"5m": 24, "15m": 64, "1h": 48, "4h": 30, "1d": 20}
# The engine fetches 200 candles per timeframe; indicators stay within that window
# (EMA100 at most), so live values match the long-history backtest closely.
MIN_BARS = 200


# --------------------------------------------------------------------------- indicators

def _ema(values: pd.Series, span: int) -> pd.Series:
    return values.ewm(span=span, adjust=False, min_periods=span).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0)


def indicator_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Indicators used by every family. ``df`` needs open/high/low/close columns."""
    out = pd.DataFrame(index=df.index)
    o, h, lo, c = (df[k].astype(float) for k in ("open", "high", "low", "close"))
    out["open"], out["high"], out["low"], out["close"] = o, h, lo, c
    prev_close = c.shift(1)
    tr = pd.concat([h - lo, (h - prev_close).abs(), (lo - prev_close).abs()], axis=1).max(axis=1)
    out["atr"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    for span in (20, 50, 100):
        out[f"ema{span}"] = _ema(c, span)
    out["rsi"] = _rsi(c)
    up, down = h.diff(), -lo.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    atr = out["atr"].replace(0, np.nan)
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / 14, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / 14, adjust=False).mean() / atr
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(0.0)
    out["adx"] = dx.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    mid = c.rolling(20).mean()
    std = c.rolling(20).std(ddof=0)
    out["bb_mid"], out["bb_std"] = mid, std
    width = (4 * std / mid.replace(0, np.nan))
    out["bb_width_rank"] = width.rolling(120, min_periods=60).rank(pct=True)
    for n in (20, 55):
        out[f"dc_high{n}"] = h.rolling(n).max().shift(1)
        out[f"dc_low{n}"] = lo.rolling(n).min().shift(1)
    vol = df["volume"].astype(float).fillna(0.0) if "volume" in df.columns else pd.Series(0.0, index=df.index)
    out["volume"] = vol
    vmean, vstd = vol.rolling(20).mean(), vol.rolling(20).std(ddof=0)
    out["volume_z"] = ((vol - vmean) / vstd.replace(0, np.nan)).fillna(0.0)
    out["has_volume"] = vol.rolling(20, min_periods=1).median() > 0
    obv = (np.sign(c.diff().fillna(0.0)) * vol).cumsum()
    out["obv"], out["obv_ema"] = obv, _ema(obv, 20)
    typical = (h + lo + c) / 3.0
    vsum = vol.rolling(20).sum()
    out["vwap20"] = (typical * vol).rolling(20).sum() / vsum.replace(0, np.nan)
    return out


def has_volume(ind: pd.DataFrame) -> bool:
    """True when most bars carry real volume (crypto, stocks, futures; not spot forex)."""
    return bool(len(ind) and float(ind["has_volume"].mean()) > 0.9)


def entry_mask(ind: pd.DataFrame, family: str, params: Mapping[str, Any], direction: str) -> pd.Series:
    """Boolean series: True on the bar whose close triggers an entry at the next bar."""
    c, long = ind["close"], direction == "long"
    p = dict(params)
    if family == "trend_pullback":
        fast, slow = ind[f"ema{p['fast']}"], ind[f"ema{p['slow']}"]
        level = float(p["rsi"]) if long else 100.0 - float(p["rsi"])
        rsi, prev = ind["rsi"], ind["rsi"].shift(1)
        if long:
            return (fast > slow) & (c > slow) & (prev < level) & (rsi >= level)
        return (fast < slow) & (c < slow) & (prev > level) & (rsi <= level)
    if family == "donchian_breakout":
        n, adx_min = int(p["n"]), float(p["adx"])
        strong = ind["adx"] >= adx_min
        return strong & ((c > ind[f"dc_high{n}"]) if long else (c < ind[f"dc_low{n}"]))
    if family == "bollinger_reversion":
        k, adx_max = float(p["k"]), float(p["adx_max"])
        calm = ind["adx"] <= adx_max
        band = ind["bb_mid"] - k * ind["bb_std"] if long else ind["bb_mid"] + k * ind["bb_std"]
        return calm & ((c < band) if long else (c > band))
    if family == "rsi_reversal":
        level = float(p["level"]) if long else 100.0 - float(p["level"])
        rsi, prev = ind["rsi"], ind["rsi"].shift(1)
        cross = (prev < level) & (rsi >= level) if long else (prev > level) & (rsi <= level)
        if int(p.get("trend") or 0):
            cross &= (c > ind["ema100"]) if long else (c < ind["ema100"])
        return cross
    if family == "squeeze_breakout":
        squeezed = ind["bb_width_rank"].shift(1) <= float(p["q"])
        upper, lower = ind["bb_mid"] + 2 * ind["bb_std"], ind["bb_mid"] - 2 * ind["bb_std"]
        return squeezed & ((c > upper) if long else (c < lower))
    if family == "atr_momentum":
        n, k = int(p["n"]), float(p["k"])
        move = c - c.shift(n)
        mask = (move > k * ind["atr"]) if long else (move < -k * ind["atr"])
        if int(p.get("trend") or 0):
            mask &= (c > ind["ema50"]) if long else (c < ind["ema50"])
        return mask
    if family == "inside_bar_breakout":
        h, lo = ind["high"], ind["low"]
        inside = (h.shift(1) <= h.shift(2)) & (lo.shift(1) >= lo.shift(2))
        mask = inside & ((c > h.shift(2)) if long else (c < lo.shift(2)))
        if int(p.get("trend") or 0):
            mask &= (c > ind["ema50"]) if long else (c < ind["ema50"])
        return mask
    if family == "volume_breakout":
        n, vz = int(p["n"]), float(p["vz"])
        loud = ind["has_volume"] & (ind["volume_z"] >= vz)
        return loud & ((c > ind[f"dc_high{n}"]) if long else (c < ind[f"dc_low{n}"]))
    if family == "obv_trend":
        level = float(p["rsi"]) if long else 100.0 - float(p["rsi"])
        rsi, prev = ind["rsi"], ind["rsi"].shift(1)
        if long:
            flow = (ind["obv"] > ind["obv_ema"]) & (c > ind["ema50"])
            return ind["has_volume"] & flow & (prev < level) & (rsi >= level)
        flow = (ind["obv"] < ind["obv_ema"]) & (c < ind["ema50"])
        return ind["has_volume"] & flow & (prev > level) & (rsi <= level)
    if family == "vwap_reversion":
        k, adx_max = float(p["k"]), float(p["adx_max"])
        calm = ind["has_volume"] & (ind["adx"] <= adx_max)
        stretch = (c - ind["vwap20"]) / ind["atr"].replace(0, np.nan)
        return calm & ((stretch <= -k) if long else (stretch >= k))
    raise ValueError(f"unknown_family:{family}")


def strategy_name(spec: Mapping[str, Any]) -> str:
    """Stable, unique display name, also the scorecard key."""
    return f"Discovered {spec['family']} {str(spec['spec_id'])[-6:]}"


# --------------------------------------------------------------------------- spec store

_cache: dict[str, Any] = {"at": 0.0, "specs": None}
_seen: dict[str, float] = {}
_seen_lock = threading.Lock()


def mode() -> str:
    value = (os.getenv("DISCOVERED_STRATEGIES_MODE") or "shadow").strip().lower()
    return value if value in {"off", "shadow", "live"} else "shadow"


def load_specs() -> list[dict[str, Any]]:
    ttl = 300.0
    if _cache["specs"] is not None and time.monotonic() - _cache["at"] < ttl:
        return _cache["specs"]
    specs: list[dict[str, Any]] = []
    try:
        from core.redis_state import state

        raw = state.get_sync(REDIS_KEY)
        payload = json.loads(raw) if raw else {}
        specs = [s for s in payload.get("specs") or [] if s.get("state") in {"shadow", "approved"}]
    except Exception:
        logger.debug("[discovered] spec load failed", exc_info=True)
    _cache.update(at=time.monotonic(), specs=specs)
    return specs


def _frame_from_candles(candles: Iterable[Any]) -> pd.DataFrame | None:
    rows = []
    for candle in candles or []:
        if isinstance(candle, Mapping):
            get = candle.get
            row = [get("open", get("o")), get("high", get("h")), get("low", get("l")), get("close", get("c")),
                   get("volume", get("v", 0.0))]
        elif isinstance(candle, (list, tuple)) and len(candle) >= 5:
            row = list(candle[1:6]) if len(candle) >= 6 else [*candle[1:5], 0.0]
        else:
            continue
        try:
            values = [float(x) for x in row[:4]]
            try:
                values.append(float(row[4] or 0.0))
            except (TypeError, ValueError):
                values.append(0.0)
            rows.append(values)
        except (TypeError, ValueError):
            continue
    if len(rows) < MIN_BARS:
        return None
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])


def _claim(key: str) -> bool:
    now = time.monotonic()
    with _seen_lock:
        if key in _seen:
            return False
        _seen[key] = now
        while len(_seen) > 8192:
            _seen.pop(next(iter(_seen)))
    return True


def _record_shadow(candidate: dict[str, Any], spec: Mapping[str, Any]) -> None:
    try:
        from engine.signal_deduplicator import get_ml_rejection_tracker
        from utils.async_runner import submit_background_coro

        features = {
            "rejection_type": "discovered_shadow",
            "strategy_name": candidate["strategy_name"],
            "strategy_group": GROUP,
            "discovered_spec_id": spec["spec_id"],
            "discovered_family": spec["family"],
            "trade_profile": spec.get("trade_profile"),
            "rr_ratio": spec["target_r"],
            "source": "discovered_strategy_shadow",
        }
        coro = get_ml_rejection_tracker().persist_rejection(
            asset=candidate["asset"],
            timeframe=candidate["timeframe"],
            direction=candidate["direction"].lower(),
            entry_price=candidate["entry"],
            stop_loss=candidate["stop"],
            take_profit_levels=[candidate["take_profit"]],
            ml_probability=None,
            rejection_reason="discovered_strategy_shadow",
            features=features,
            rejection_type="discovered_shadow",
        )
        submit_background_coro(coro, label="discovered_strategy_shadow")
    except Exception:
        logger.debug("[discovered] shadow record failed", exc_info=True)


def discovered_candidates(asset: str, timeframe: str, data: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Evaluate published specs for one asset and timeframe on the engine's candles."""
    current_mode = mode()
    if current_mode == "off":
        return []
    wanted = _TF_ALIASES.get(str(timeframe).lower(), str(timeframe).lower())
    specs = [
        s for s in load_specs()
        if str(s.get("asset", "")).upper() == str(asset).upper() and s.get("timeframe") == wanted
    ]
    if not specs:
        return []
    df = _frame_from_candles((data or {}).get("candles"))
    if df is None:
        return []
    ind = indicator_frame(df)
    # The last candle may still be forming: decide on the last closed bar.
    signal_row = len(ind) - 2
    price = float(ind["close"].iloc[-1])
    atr = float(ind["atr"].iloc[signal_row])
    if not (math.isfinite(price) and price > 0 and math.isfinite(atr) and atr > 0):
        return []
    out: list[dict[str, Any]] = []
    for spec in specs:
        try:
            direction = spec["direction"]
            if not bool(entry_mask(ind, spec["family"], spec["params"], direction).iloc[signal_row]):
                continue
            risk = float(spec["stop_atr"]) * atr
            sign = 1.0 if direction == "long" else -1.0
            candidate = {
                "asset": str(asset).upper(),
                "timeframe": timeframe,
                "direction": "LONG" if direction == "long" else "SHORT",
                "entry": price,
                "stop": price - sign * risk,
                "stop_loss": price - sign * risk,
                "take_profit": price + sign * float(spec["target_r"]) * risk,
                "confidence": 0.6,
                "strategy_name": strategy_name(spec),
                "strategy_group": GROUP,
                "reasoning": (
                    f"{spec['family']} {spec['params']} found on {spec.get('data_source', 'history')} data; "
                    f"out-of-sample {spec['metrics']['oos']['trades']} trades, "
                    f"{spec['metrics']['oos']['expectancy_r']:+.2f}R per trade after costs"
                ),
                "discovered_spec_id": spec["spec_id"],
                "discovered_state": spec.get("state"),
                "trade_profile": spec.get("trade_profile") or "swing",
            }
            bar_key = f"{spec['spec_id']}|{len(df)}|{ind['close'].iloc[signal_row]:.10g}"
            if not _claim(bar_key):
                continue
            if current_mode == "live" and spec.get("state") == "approved":
                out.append(candidate)
            else:
                _record_shadow(candidate, spec)
        except Exception:
            logger.debug("[discovered] spec failed id=%s", spec.get("spec_id"), exc_info=True)
    return out


__all__ = [
    "EXIT_GRID",
    "FAMILY_GRID",
    "STYLES",
    "VOLUME_FAMILIES",
    "has_volume",
    "GROUP",
    "MAX_HOLD_BARS",
    "REDIS_KEY",
    "discovered_candidates",
    "entry_mask",
    "indicator_frame",
    "load_specs",
    "mode",
    "strategy_name",
]
