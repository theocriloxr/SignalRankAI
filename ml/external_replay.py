"""Extra training rows from long public market history (owner request, 8 Nov 2026).

"Retrain on more data, even data you can source from the internet, in addition
to everything the bot has." The bot's own outcomes stay the anchor; this adds
labelled setups replayed on years of public candles:

* Source: the same public feeds strategy discovery already uses
  (Binance public market data for crypto, Yahoo chart history otherwise) via
  ``ml.strategy_discovery.load_history``. No keys, no broker calls.
* Setups: the deterministic entry families in ``strategies.discovered`` (trend
  pullback, Donchian/volume/squeeze breakouts, RSI/Bollinger/VWAP reversion,
  ATR momentum ...) on the instruments and timeframes the bot actually trades.
* Label: the trainer's own rule. Enter at the next bar's open, stop 1 ATR,
  TP1 at ``ML_EXTERNAL_REPLAY_TP1_R`` (default 1.5R); TP1 first is a win, stop
  first (or both in one bar) is a loss, the time stop is a loss with barrier
  ``time``. Costs are not needed for a TP1/stop label.
* Features: the versioned live contract (velocity, ATR, volume, ADX, higher
  timeframe trend from closed bars only), so nothing a live signal would not
  know is used.

Guards that keep the quality gate honest:

* Every replayed bar is older than the oldest row of the bot's own evidence,
  and replay rows never exceed ``ML_EXTERNAL_REPLAY_MAX_RATIO`` (default and
  maximum 2.0) times the bot's rows. With the chronological 70/15/15 split this
  puts every replay row in the model-fit window: calibration, validation, the
  promotion quality gate and the champion comparison are measured on the bot's
  own outcomes only.
* Low weight (``ML_EXTERNAL_REPLAY_WEIGHT``, default 0.25) on top of the
  trainer's recency decay. Fetched history is cached on disk for a day.
"""
from __future__ import annotations

import json
import logging
import os
import time
from io import StringIO
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SOURCE_TYPE = "external_replay"
_TF_SECONDS = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
_HOLD = {"5m": 24, "15m": 32, "1h": 24, "4h": 30, "1d": 20}
_HIGHER = {"5m": ("1h", "4h"), "15m": ("1h", "4h"), "1h": ("4h", "1d"), "4h": ("4h", "1d"), "1d": ("1d", "1d")}


def _env_float(name: str, default: float, lo: float, hi: float) -> float:
    try:
        value = float(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        value = default
    return max(lo, min(hi, value))


def enabled() -> bool:
    return str(os.getenv("ML_EXTERNAL_REPLAY_ENABLED", "true")).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_tf(tf: Any) -> str:
    text = str(tf or "").strip().lower()
    return {"24h": "1d", "d": "1d", "60m": "1h", "240m": "4h"}.get(text, text)


# --------------------------------------------------------------------------- history (cached)

def _cache_dir() -> Path:
    return Path(os.getenv("ML_EXTERNAL_REPLAY_CACHE_DIR") or "/tmp/signalrank_external_history")


def _cached_history(symbol: str, klass: str, client: Any) -> dict[str, pd.DataFrame]:
    path = _cache_dir() / f"{symbol.replace('/', '_')}.json"
    ttl = _env_float("ML_EXTERNAL_REPLAY_CACHE_HOURS", 24.0, 1.0, 24.0 * 30) * 3600
    try:
        if path.exists() and time.time() - path.stat().st_mtime < ttl:
            raw = json.loads(path.read_text("utf-8"))
            frames = {}
            for tf, body in raw.items():
                frame = pd.read_json(StringIO(body), orient="split")
                frame.index = pd.to_datetime(frame.index, utc=True)
                frames[tf] = frame
            return frames
    except Exception:
        pass
    from ml.strategy_discovery import load_history

    frames, _source = load_history(symbol, klass, client)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({tf: f.to_json(orient="split", date_format="iso") for tf, f in frames.items()}),
                        "utf-8")
    except Exception:
        pass
    return frames


# --------------------------------------------------------------------------- labelling

def label_entries(ind: pd.DataFrame, bars: np.ndarray, direction: str, stop_atr: float, tp1_r: float,
                  hold: int) -> list[tuple[int, float, float, float, str]]:
    """(signal bar, entry, stop, tp1, barrier) for each entry; barrier is upper|lower|time."""
    o, h, lo, atr = (ind[k].to_numpy(float) for k in ("open", "high", "low", "atr"))
    n, long, out = len(ind), direction == "long", []
    for i in bars:
        j = i + 1
        if j >= n or not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        entry = o[j]
        risk = stop_atr * atr[i]
        stop = entry - risk if long else entry + risk
        tp1 = entry + tp1_r * risk if long else entry - tp1_r * risk
        barrier = "time"
        for k in range(j, min(n, j + hold)):
            hit_stop = lo[k] <= stop if long else h[k] >= stop
            hit_tp = h[k] >= tp1 if long else lo[k] <= tp1
            if hit_stop:  # both in one bar counts as a loss (conservative)
                barrier = "lower"
                break
            if hit_tp:
                barrier = "upper"
                break
        else:
            if j + hold > n:
                continue  # not yet resolved at the end of the data
        out.append((int(i), float(entry), float(stop), float(tp1), barrier))
    return out


def _closed_higher_trend(index: pd.DatetimeIndex, higher: pd.DataFrame | None, tf: str) -> np.ndarray:
    """SMA20 vs SMA50 of the higher timeframe, using only bars closed before each signal bar."""
    if higher is None or higher.empty or len(higher) < 60:
        return np.zeros(len(index))
    higher = higher.copy()
    higher.index = pd.to_datetime(higher.index, utc=True)
    close = higher["close"].astype(float)
    trend = np.sign(close.rolling(20).mean() - close.rolling(50).mean()).fillna(0.0)
    closes_at = higher.index + pd.Timedelta(seconds=_TF_SECONDS.get(tf, 3600))
    series = pd.Series(trend.to_numpy(), index=closes_at)
    return series.reindex(index, method="ffill").fillna(0.0).to_numpy()


def replay_frame(asset: str, klass: str, tf: str, df: pd.DataFrame, frames: Mapping[str, pd.DataFrame], *,
                 before: pd.Timestamp | None, max_rows: int) -> list[dict[str, Any]]:
    """Labelled training rows for one asset/timeframe, newest first, all strictly before ``before``."""
    from ml.features import _asset_class_to_int
    from strategies.discovered import FAMILY_GRID, VOLUME_FAMILIES, entry_mask, has_volume, indicator_frame

    if df is None or len(df) < 400:
        return []
    df = df.copy()
    df.index = pd.to_datetime(df.index, utc=True)
    ind = indicator_frame(df).iloc[120:]
    if before is not None:
        cutoff = pd.Timestamp(before)
        cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
        ind = ind[ind.index < cutoff]
    if len(ind) < 300:
        return []
    hold = _HOLD.get(tf, 24)
    tp1_r = _env_float("ML_EXTERNAL_REPLAY_TP1_R", 1.5, 0.5, 5.0)
    close = ind["close"]
    tr = pd.concat([ind["high"] - ind["low"], (ind["high"] - close.shift(1)).abs(),
                    (ind["low"] - close.shift(1)).abs()], axis=1).max(axis=1)
    atr14, atr50 = tr.rolling(14).mean(), tr.rolling(50).mean()
    vol = ind["volume"].astype(float)
    rel_vol = (vol / vol.shift(1).rolling(20).mean()).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    vel = {n: close.pct_change(n).fillna(0.0) for n in (3, 5, 10)}
    h1, h2 = _HIGHER.get(tf, ("4h", "1d"))
    mtf4 = _closed_higher_trend(ind.index, frames.get(h1), h1)
    mtf1d = _closed_higher_trend(ind.index, frames.get(h2), h2)
    volume_ok = has_volume(ind)
    class_enc = float(_asset_class_to_int(asset))

    taken: dict[tuple[int, str], str] = {}
    for family, grid in FAMILY_GRID.items():
        if family in VOLUME_FAMILIES and not volume_ok:
            continue
        params = grid[len(grid) // 2]  # one representative setting per family
        for direction in ("long", "short"):
            mask = entry_mask(ind, family, params, direction).fillna(False).to_numpy(bool)
            for i in np.flatnonzero(mask):
                taken.setdefault((int(i), direction), family)
    rows: list[dict[str, Any]] = []
    by_direction: dict[str, list[int]] = {"long": [], "short": []}
    for (i, direction) in taken:
        by_direction[direction].append(i)
    weight = _env_float("ML_EXTERNAL_REPLAY_WEIGHT", 0.25, 0.0, 1.0)
    for direction, bars in by_direction.items():
        for i, entry, stop, tp1, barrier in label_entries(ind, np.array(sorted(bars), dtype=int), direction,
                                                          1.0, tp1_r, hold):
            adx = float(ind["adx"].iloc[i]) if np.isfinite(ind["adx"].iloc[i]) else 0.0
            a14, a50, c = float(atr14.iloc[i] or 0.0), float(atr50.iloc[i] or 0.0), float(close.iloc[i])
            ts = ind.index[i]
            rows.append({
                "signal_id": f"replay:{asset}:{tf}:{direction}:{int(ts.timestamp())}",
                "asset": asset, "timeframe": tf, "direction": direction,
                "strategy_name": f"replay_{taken[(i, direction)]}",
                "regime": "trending" if adx >= 25 else "ranging",
                "entry": entry, "stop_loss": stop, "take_profit": tp1, "rr_ratio": tp1_r,
                "score": 0.0, "strength": 0.5,
                "price_velocity_3": float(vel[3].iloc[i]), "price_velocity_5": float(vel[5].iloc[i]),
                "price_velocity_10": float(vel[10].iloc[i]),
                "price_acceleration_3_10": float(vel[3].iloc[i] - vel[10].iloc[i]),
                "atr_rel": (a14 / c) if c > 0 and np.isfinite(a14) else 0.0,
                "atr_regime": (a14 / a50) if a50 and np.isfinite(a50) and np.isfinite(a14) else 0.0,
                "relative_volume": float(rel_vol.iloc[i]) if volume_ok else 0.0,
                "mtf_4h_trend": float(mtf4[i]), "mtf_1d_trend": float(mtf1d[i]),
                "funding_rate": 0.0, "open_interest_change": 0.0, "asset_class_enc": class_enc, "adx": adx,
                "dxy_trend": 0.0, "vix_trend": 0.0, "us10y_trend": 0.0, "yield_spread": 0.0,
                "minutes_since_high_impact_news": 0.0, "minutes_until_high_impact_news": 0.0,
                "news_event_impact_score": 0.0, "spx_trend": 0.0, "btc_corr": 0.0,
                "partial_tp_progress": 0.0, "false_breakout": 0, "barrier_type": barrier,
                "sample_weight": weight, "source_type": SOURCE_TYPE, "source_weight": weight,
                "created_at": (ts.tz_convert(None) if ts.tzinfo else ts).to_pydatetime(),
                "target": 1 if barrier == "upper" else 0,
            })
    return _balanced_newest(rows, max_rows)


def _balanced_newest(rows: list[dict[str, Any]], max_rows: int) -> list[dict[str, Any]]:
    """Newest rows, taken round-robin across setup families so one family cannot dominate."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in sorted(rows, key=lambda r: r["created_at"], reverse=True):
        groups.setdefault(row["strategy_name"], []).append(row)
    picked: list[dict[str, Any]] = []
    depth = 0
    while len(picked) < max_rows and any(len(g) > depth for g in groups.values()):
        for group in groups.values():
            if depth < len(group) and len(picked) < max_rows:
                picked.append(group[depth])
        depth += 1
    return picked


# --------------------------------------------------------------------------- training integration

def _asset_class(asset: str) -> str:
    from ml.strategy_discovery import asset_class

    return asset_class(asset)


def build_rows(pairs: Iterable[tuple[str, str]], *, before: pd.Timestamp | None, budget_rows: int,
               client: Any = None, deadline: float | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Replay rows for (asset, timeframe) pairs, spread evenly, within ``budget_rows`` and a time budget."""
    import httpx

    pairs = sorted({(str(a).upper(), _normalize_tf(t)) for a, t in pairs if a and _normalize_tf(t) in _TF_SECONDS})
    report: dict[str, Any] = {"pairs": len(pairs), "assets": {}, "skipped": []}
    if not pairs or budget_rows <= 0:
        return [], report
    per_pair = max(1, budget_rows // len(pairs))
    owns = client is None
    client = client or httpx.Client(timeout=20.0, headers={"User-Agent": "signalrank-research/1.0"})
    rows: list[dict[str, Any]] = []
    history: dict[str, dict[str, pd.DataFrame]] = {}
    try:
        for asset, tf in pairs:
            if deadline is not None and time.monotonic() > deadline:
                report["skipped"].append(f"{asset}:{tf}:time_budget")
                continue
            try:
                if asset not in history:
                    history[asset] = _cached_history(asset, _asset_class(asset), client)
                frames = history[asset]
                found = replay_frame(asset, _asset_class(asset), tf, frames.get(tf), frames,
                                     before=before, max_rows=per_pair)
            except Exception as exc:
                report["skipped"].append(f"{asset}:{tf}:{type(exc).__name__}")
                continue
            rows.extend(found)
            report["assets"][f"{asset}:{tf}"] = len(found)
    finally:
        if owns:
            client.close()
    return rows[:budget_rows], report


def augment(df: pd.DataFrame, *, client: Any = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Append replay rows to the bot's dataset under the guards in the module docstring."""
    evidence: dict[str, Any] = {"enabled": enabled(), "applied": False, "source_type": SOURCE_TYPE}
    if not enabled():
        return df, evidence
    if df is None or df.empty or not {"asset", "timeframe", "created_at"} <= set(df.columns):
        evidence["reason"] = "no_internal_rows"
        return df, evidence
    internal = df[df.get("source_type", pd.Series("", index=df.index)).astype(str) != SOURCE_TYPE]
    ratio = _env_float("ML_EXTERNAL_REPLAY_MAX_RATIO", 2.0, 0.0, 2.0)
    budget = int(len(internal) * ratio)
    if budget <= 0:
        evidence["reason"] = "ratio_zero"
        return df, evidence
    oldest = pd.to_datetime(internal["created_at"], errors="coerce").min()
    if pd.isna(oldest):
        evidence["reason"] = "internal_timestamps_unavailable"
        return df, evidence
    before = pd.Timestamp(oldest).tz_localize("UTC") if pd.Timestamp(oldest).tzinfo is None else pd.Timestamp(oldest)
    deadline = time.monotonic() + _env_float("ML_EXTERNAL_REPLAY_TIMEOUT_SECONDS", 240.0, 10.0, 3600.0)
    pairs = list(internal[["asset", "timeframe"]].dropna().itertuples(index=False, name=None))
    rows, report = build_rows(pairs, before=before, budget_rows=budget, client=client, deadline=deadline)
    evidence.update(report)
    if not rows:
        evidence["reason"] = "no_replay_rows"
        return df, evidence
    extra = pd.DataFrame(rows)
    # Same exclusions as the bot's own rows (pegged tokens, focused universe).
    try:
        from ml.train_model import _exclude_pegged_assets, _restrict_to_focused_universe

        extra, _ = _exclude_pegged_assets(extra)
        extra, _ = _restrict_to_focused_universe(extra)
    except Exception:
        pass
    combined = pd.concat([df, extra], ignore_index=True, sort=False)
    combined.attrs.update(dict(getattr(df, "attrs", {}) or {}))
    counts = dict(combined.attrs.get("source_counts") or {})
    counts[SOURCE_TYPE] = int(len(extra))
    combined.attrs["source_counts"] = counts
    evidence.update({
        "applied": True, "rows": int(len(extra)), "internal_rows": int(len(internal)),
        "before": before.isoformat(), "win_rate": round(float(extra["target"].mean()), 4) if len(extra) else None,
    })
    combined.attrs["external_replay"] = evidence
    return combined, evidence
