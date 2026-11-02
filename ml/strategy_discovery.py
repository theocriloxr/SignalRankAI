"""Discover per-asset strategies from long external price history (2 Nov 2026).

Run on the analytics role (``python -m ml.strategy_discovery``) or by the
weekly loop in ``runtime/analytics.py``. For every asset in the engine's
universe and each research timeframe it:

1. loads years of history from public market data (Binance public data for
   crypto since 2019; Yahoo Finance for forex, stocks, indices and commodities:
   about 730 days of hourly bars and decades of daily bars), falling back to
   SignalRank's own ``market_candles``;
2. backtests every rule family x parameter set x stop/target x direction in
   ``strategies/discovered.py`` with next-bar entries, stop-first when stop and
   target share a bar, a time stop, and per-class trading costs;
3. selects on the first 60% of history only (enough trades, positive
   expectancy, t-statistic, positive in most sub-periods), checks the ten best
   on the next 20%, and keeps a rule only if it is also profitable on the final
   20%, which no earlier step has seen;
4. re-tests the specs already published on the newest data, retires those that
   have decayed, and approves or retires them from their forward record in the
   per-asset strategy scorecard;
5. publishes the specs to Redis for ``strategies.discovered``.

Nothing here sends a signal. New specs start in ``shadow``; a spec becomes
``approved`` only after its own forward-tracked outcomes show a supported edge.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from strategies.discovered import (
    EXIT_GRID,
    FAMILY_GRID,
    MAX_HOLD_BARS,
    REDIS_KEY,
    entry_mask,
    indicator_frame,
    strategy_name,
)

logger = logging.getLogger(__name__)

RESEARCH_TIMEFRAMES = ("1h", "4h", "1d")
DEFAULT_COSTS = {"crypto": 0.0015, "forex": 0.0002, "fx": 0.0002, "stocks": 0.0010, "stock": 0.0010,
                 "indices": 0.0005, "index": 0.0005, "commodities": 0.0008, "commodity": 0.0008}

YAHOO_SYMBOLS = {
    "US500": "^GSPC", "SPX500": "^GSPC", "NAS100": "^NDX", "US100": "^NDX", "US30": "^DJI", "GER40": "^GDAXI",
    "DE40": "^GDAXI", "UK100": "^FTSE", "JP225": "^N225", "FRA40": "^FCHI", "EU50": "^STOXX50E",
    "AUS200": "^AXJO", "HK50": "^HSI", "US2000": "^RUT", "VIX": "^VIX", "CN50": "XIN9.FGI", "IN50": "^NSEI",
    "XAUUSD": "GC=F", "XAGUSD": "SI=F", "WTI": "CL=F", "USOIL": "CL=F", "BRENT": "BZ=F", "UKOIL": "BZ=F",
    "NATGAS": "NG=F", "XNGUSD": "NG=F", "COPPER": "HG=F", "XCUUSD": "HG=F", "XPTUSD": "PL=F",
    "PLATINUM": "PL=F", "XPDUSD": "PA=F", "PALLADIUM": "PA=F", "CORN": "ZC=F", "WHEAT": "ZW=F",
    "SOYBEAN": "ZS=F", "COFFEE": "KC=F", "SUGAR": "SB=F", "COCOA": "CC=F", "COTTON": "CT=F",
}

_HEADERS = {"User-Agent": "Mozilla/5.0 (SignalRank research)"}


def _env_float(name: str, default: float) -> float:
    try:
        value = float((os.getenv(name) or str(default)).strip())
        return value if math.isfinite(value) else default
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    return int(_env_float(name, float(default)))


def asset_class(symbol: str) -> str:
    try:
        from services.asset_mapper import classify_asset

        value = str(classify_asset(symbol) or "").lower()
        if value:
            return value
    except Exception:
        pass
    upper = symbol.upper()
    if upper.endswith(("USDT", "USDC")):
        return "crypto"
    if upper in YAHOO_SYMBOLS:
        return "indices" if YAHOO_SYMBOLS[upper].startswith("^") else "commodities"
    if len(upper) == 6 and upper.isalpha():
        return "forex"
    return "stocks"


def cost_fraction(klass: str) -> float:
    overrides = {}
    try:
        overrides = json.loads(os.getenv("DISCOVERY_COSTS_JSON") or "{}")
    except ValueError:
        pass
    return float(overrides.get(klass, DEFAULT_COSTS.get(klass, 0.001)))


def default_universe() -> list[str]:
    raw = os.getenv("DISCOVERY_ASSETS") or os.getenv("TRADABLE_ASSETS") or ""
    symbols = [s.strip().upper() for s in raw.replace(";", ",").split(",") if s.strip()]
    try:
        from core.pegged_assets import filter_pegged

        symbols = filter_pegged(symbols)
    except Exception:
        pass
    return list(dict.fromkeys(symbols))


# --------------------------------------------------------------------------- data

def _frame(rows: Iterable[tuple[int, float, float, float, float]]) -> pd.DataFrame:
    df = pd.DataFrame(list(rows), columns=["ts", "open", "high", "low", "close"])
    if df.empty:
        return df
    df = df.dropna().drop_duplicates("ts").sort_values("ts")
    df = df[(df["high"] >= df["low"]) & (df["close"] > 0)]
    df.index = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df[["open", "high", "low", "close"]]


def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.resample(rule, origin="epoch").agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    return out.dropna()


def fetch_binance(symbol: str, interval: str, start_ms: int, client: Any) -> pd.DataFrame:
    base = os.getenv("DISCOVERY_BINANCE_URL") or "https://data-api.binance.vision/api/v3/klines"
    rows: list[tuple[int, float, float, float, float]] = []
    cursor = start_ms
    for _ in range(_env_int("DISCOVERY_BINANCE_MAX_PAGES", 120)):
        resp = client.get(base, params={"symbol": symbol, "interval": interval, "startTime": cursor, "limit": 1000})
        if resp.status_code != 200:
            break
        batch = resp.json()
        if not batch:
            break
        rows.extend((int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4])) for k in batch)
        if len(batch) < 1000:
            break
        cursor = int(batch[-1][0]) + 1
        time.sleep(0.05)
    return _frame(rows)


def fetch_yahoo(symbol: str, interval: str, client: Any) -> pd.DataFrame:
    params: dict[str, Any] = {"interval": interval, "includePrePost": "false"}
    if interval == "1h":
        params["range"] = "730d"
    else:
        params.update(period1=0, period2=int(time.time()))
    resp = client.get(f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}", params=params)
    if resp.status_code != 200:
        return _frame([])
    result = ((resp.json().get("chart") or {}).get("result") or [None])[0] or {}
    stamps = result.get("timestamp") or []
    quote = (((result.get("indicators") or {}).get("quote")) or [{}])[0]
    rows = []
    for i, ts in enumerate(stamps):
        try:
            rows.append((int(ts) * 1000, float(quote["open"][i]), float(quote["high"][i]), float(quote["low"][i]),
                         float(quote["close"][i])))
        except (TypeError, KeyError, IndexError):
            continue
    return _frame(rows)


def yahoo_symbol(symbol: str, klass: str) -> str:
    upper = symbol.upper()
    if upper in YAHOO_SYMBOLS:
        return YAHOO_SYMBOLS[upper]
    if klass in {"forex", "fx"}:
        return f"{upper}=X"
    return upper.replace(".", "-")


async def stored_history(symbol: str, timeframe: str) -> pd.DataFrame:
    """SignalRank's own candles, used when no external source answers."""
    try:
        from sqlalchemy import text

        from db.session import get_session

        async with get_session(priority="analytics", label="discovery.candles", timeout_seconds=60,
                               drop_if_busy=False) as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT open_time_ms, open, high, low, close FROM market_candles "
                        "WHERE symbol = :s AND timeframe = :tf ORDER BY open_time_ms"
                    ),
                    {"s": symbol, "tf": timeframe},
                )
            ).all()
        return _frame((int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])) for r in rows)
    except Exception:
        logger.debug("[discovery] stored history failed %s %s", symbol, timeframe, exc_info=True)
        return _frame([])


def load_history(symbol: str, klass: str, client: Any) -> tuple[dict[str, pd.DataFrame], str]:
    """Return {timeframe: frame} and a source label."""
    frames: dict[str, pd.DataFrame] = {}
    if klass == "crypto":
        start = int(pd.Timestamp(os.getenv("DISCOVERY_CRYPTO_START") or "2019-01-01", tz="UTC").timestamp() * 1000)
        hourly = fetch_binance(symbol, "1h", start, client)
        if not hourly.empty:
            frames["1h"] = hourly
            frames["4h"] = _resample(hourly, "4h")
            daily = fetch_binance(symbol, "1d", start, client)
            frames["1d"] = daily if not daily.empty else _resample(hourly, "1D")
            return frames, "binance"
    ysym = yahoo_symbol(symbol, klass)
    hourly = fetch_yahoo(ysym, "1h", client)
    daily = fetch_yahoo(ysym, "1d", client)
    if not hourly.empty:
        frames["1h"] = hourly
        frames["4h"] = _resample(hourly, "4h")
    if not daily.empty:
        frames["1d"] = daily
    return frames, "yahoo"


# --------------------------------------------------------------------------- backtest

def backtest(ind: pd.DataFrame, mask: pd.Series, direction: str, stop_atr: float, target_r: float,
             hold: int, cost: float) -> tuple[np.ndarray, np.ndarray]:
    """Non-overlapping trades. Returns (signal bar index, net R) arrays."""
    sig = np.flatnonzero(mask.to_numpy(dtype=bool, na_value=False))
    n = len(ind)
    sig = sig[(sig + 1 + hold) < n]
    if sig.size == 0:
        return np.empty(0, dtype=int), np.empty(0)
    op = ind["open"].to_numpy(float)
    hi = ind["high"].to_numpy(float)
    lo = ind["low"].to_numpy(float)
    cl = ind["close"].to_numpy(float)
    atr = ind["atr"].to_numpy(float)
    entry = op[sig + 1]
    risk = stop_atr * atr[sig]
    ok = np.isfinite(risk) & (risk > 0) & np.isfinite(entry) & (entry > 0)
    sig, entry, risk = sig[ok], entry[ok], risk[ok]
    if sig.size == 0:
        return np.empty(0, dtype=int), np.empty(0)
    sign = 1.0 if direction == "long" else -1.0
    stop = entry - sign * risk
    target = entry + sign * target_r * risk
    offsets = np.arange(hold)
    idx = sig[:, None] + 1 + offsets[None, :]
    win_hi, win_lo = hi[idx], lo[idx]
    if sign > 0:
        hit_stop, hit_tgt = win_lo <= stop[:, None], win_hi >= target[:, None]
    else:
        hit_stop, hit_tgt = win_hi >= stop[:, None], win_lo <= target[:, None]
    big = hold + 1
    first_stop = np.where(hit_stop.any(1), hit_stop.argmax(1), big)
    first_tgt = np.where(hit_tgt.any(1), hit_tgt.argmax(1), big)
    r = np.where(first_stop <= first_tgt, -1.0, target_r)  # stop first when both share a bar
    timed = (first_stop == big) & (first_tgt == big)
    last_close = cl[sig + hold]
    r = np.where(timed, sign * (last_close - entry) / risk, r)
    exit_off = np.minimum(np.minimum(first_stop, first_tgt), hold - 1)
    r = r - cost * entry / risk
    # keep only trades that start after the previous one exited
    keep = np.zeros(sig.size, dtype=bool)
    free_at = -1
    exits = sig + 1 + exit_off
    for i in range(sig.size):
        if sig[i] > free_at:
            keep[i] = True
            free_at = exits[i]
    return sig[keep], r[keep]


def metrics(r: np.ndarray) -> dict[str, Any]:
    n = int(r.size)
    if n == 0:
        return {"trades": 0, "win_rate": None, "expectancy_r": 0.0, "t_stat": 0.0, "profit_factor": 0.0,
                "max_drawdown_r": 0.0}
    mean = float(r.mean())
    std = float(r.std(ddof=1)) if n > 1 else 0.0
    gains, losses = float(r[r > 0].sum()), float(-r[r < 0].sum())
    equity = np.cumsum(r)
    drawdown = float((np.maximum.accumulate(equity) - equity).max())
    return {
        "trades": n,
        "win_rate": round(float((r > 0).mean()), 4),
        "expectancy_r": round(mean, 4),
        "t_stat": round(mean / (std / math.sqrt(n)), 3) if std > 0 else 0.0,
        "profit_factor": round(gains / losses, 3) if losses > 0 else (99.0 if gains > 0 else 0.0),
        "max_drawdown_r": round(drawdown, 2),
    }


@dataclass
class Rules:
    is_frac: float = 0.6
    oos1_frac: float = 0.2
    min_is_trades: int = 30
    min_oos_trades: int = 10
    min_is_expectancy: float = 0.05
    min_is_t: float = 2.0
    min_positive_segments: float = 0.6
    oos_checks: int = 10
    keep_per_tf: int = 3

    @classmethod
    def from_env(cls) -> "Rules":
        return cls(
            min_is_trades=_env_int("DISCOVERY_MIN_IS_TRADES", 30),
            min_oos_trades=_env_int("DISCOVERY_MIN_OOS_TRADES", 10),
            min_is_expectancy=_env_float("DISCOVERY_MIN_IS_EXPECTANCY_R", 0.05),
            min_is_t=_env_float("DISCOVERY_MIN_IS_T", 2.0),
            oos_checks=_env_int("DISCOVERY_OOS_CHECKS", 10),
            keep_per_tf=_env_int("DISCOVERY_KEEP_PER_TIMEFRAME", 3),
        )


def spec_id(asset: str, tf: str, family: str, params: Mapping[str, Any], direction: str, stop: float,
            target: float) -> str:
    raw = json.dumps([asset, tf, family, dict(sorted(params.items())), direction, stop, target])
    return "ds_" + hashlib.sha1(raw.encode()).hexdigest()[:12]


def research_frame(asset: str, klass: str, tf: str, df: pd.DataFrame, rules: Rules) -> dict[str, Any]:
    """Search every rule on one asset/timeframe. Returns survivors and counts."""
    ind = indicator_frame(df).iloc[120:]  # drop indicator warm-up
    n = len(ind)
    if n < 600:
        return {"survivors": [], "configs": 0, "bars": n, "skipped": "too_little_history"}
    hold = MAX_HOLD_BARS.get(tf, 30)
    cost = cost_fraction(klass)
    is_end, oos1_end = int(n * rules.is_frac), int(n * (rules.is_frac + rules.oos1_frac))
    passed_is: list[dict[str, Any]] = []
    configs = 0
    for family, grid in FAMILY_GRID.items():
        for params in grid:
            for direction in ("long", "short"):
                mask = entry_mask(ind, family, params, direction)
                for stop_atr, target_r in EXIT_GRID:
                    configs += 1
                    bars, r = backtest(ind, mask, direction, stop_atr, target_r, hold, cost)
                    in_is = bars < is_end
                    r_is = r[in_is]
                    m_is = metrics(r_is)
                    if (m_is["trades"] < rules.min_is_trades or m_is["expectancy_r"] < rules.min_is_expectancy
                            or m_is["t_stat"] < rules.min_is_t):
                        continue
                    segments = np.array_split(r_is, 4)
                    if np.mean([seg.sum() > 0 for seg in segments]) < rules.min_positive_segments:
                        continue
                    passed_is.append({"family": family, "params": params, "direction": direction,
                                      "stop_atr": stop_atr, "target_r": target_r, "bars": bars, "r": r,
                                      "is": m_is})
    passed_is.sort(key=lambda c: c["is"]["t_stat"], reverse=True)
    survivors = []
    for cand in passed_is[: rules.oos_checks]:
        bars, r = cand["bars"], cand["r"]
        r1 = r[(bars >= is_end) & (bars < oos1_end)]
        r2 = r[bars >= oos1_end]
        m1, m2 = metrics(r1), metrics(r2)
        if m1["trades"] < rules.min_oos_trades or m1["expectancy_r"] <= 0:
            continue
        if m2["trades"] < rules.min_oos_trades or m2["expectancy_r"] <= 0:
            continue
        m_oos = metrics(np.concatenate([r1, r2]))
        if m_oos["profit_factor"] < 1.15:
            continue
        survivors.append({
            "spec_id": spec_id(asset, tf, cand["family"], cand["params"], cand["direction"], cand["stop_atr"],
                               cand["target_r"]),
            "asset": asset, "asset_class": klass, "timeframe": tf, "family": cand["family"],
            "params": cand["params"], "direction": cand["direction"], "stop_atr": cand["stop_atr"],
            "target_r": cand["target_r"], "max_hold_bars": hold, "cost_fraction": cost,
            "metrics": {"in_sample": cand["is"], "validation": m1, "holdout": m2, "oos": m_oos},
            "data_from": str(ind.index[0].date()), "data_to": str(ind.index[-1].date()), "bars": n,
        })
    survivors.sort(key=lambda s: s["metrics"]["oos"]["expectancy_r"] * math.sqrt(s["metrics"]["oos"]["trades"]),
                   reverse=True)
    picked, families = [], set()
    for s in survivors:
        if s["family"] in families:
            continue
        families.add(s["family"])
        picked.append(s)
        if len(picked) >= rules.keep_per_tf:
            break
    return {"survivors": picked, "configs": configs, "bars": n, "passed_in_sample": len(passed_is)}


def recheck_spec(spec: Mapping[str, Any], df: pd.DataFrame) -> dict[str, Any]:
    """Backtest an existing spec on the newest 20% of history."""
    ind = indicator_frame(df).iloc[120:]
    n = len(ind)
    mask = entry_mask(ind, spec["family"], spec["params"], spec["direction"])
    bars, r = backtest(ind, mask, spec["direction"], float(spec["stop_atr"]), float(spec["target_r"]),
                       int(spec.get("max_hold_bars") or MAX_HOLD_BARS.get(spec["timeframe"], 30)),
                       float(spec.get("cost_fraction") or 0.001))
    return metrics(r[bars >= int(n * 0.8)])


# --------------------------------------------------------------------------- lifecycle

def _forward_verdict(spec: Mapping[str, Any]) -> str | None:
    """Approve or retire from the spec's own forward-tracked outcomes."""
    try:
        from core.redis_state import state
        from services.strategy_scorecard import REDIS_KEY as SCORECARD_KEY, adjustment_for_cell

        raw = state.get_sync(SCORECARD_KEY)
        cells = (json.loads(raw) if raw else {}).get("cells") or {}
        key = f"{spec['asset'].upper()}|{spec['timeframe'].lower()}|{strategy_name(spec).lower()}"
        multiplier, reason = adjustment_for_cell((cells.get("asset_tf") or {}).get(key))
        if reason == "supported_edge":
            return "approved"
        if reason == "supported_negative_edge":
            return "retired"
    except Exception:
        logger.debug("[discovery] forward verdict failed", exc_info=True)
    return None


def merge_specs(existing: list[dict[str, Any]], found: list[dict[str, Any]],
                rechecks: Mapping[str, dict[str, Any]]) -> list[dict[str, Any]]:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    by_id = {s["spec_id"]: dict(s) for s in existing}
    for spec in found:
        prior = by_id.get(spec["spec_id"])
        merged = {**spec, "state": (prior or {}).get("state", "shadow"),
                  "discovered_at": (prior or {}).get("discovered_at", now), "revalidated_at": now}
        if merged["state"] == "retired" and (prior or {}).get("retired_reason") == "decayed_recent_backtest":
            merged["state"] = "shadow"  # it passed the full walk-forward again
        by_id[spec["spec_id"]] = merged
    for sid, spec in by_id.items():
        recent = rechecks.get(sid)
        if recent is not None:
            spec["recent_backtest"] = recent
            if recent["trades"] >= 10 and recent["expectancy_r"] < -0.05 and spec.get("state") != "retired":
                spec["state"], spec["retired_reason"], spec["retired_at"] = "retired", "decayed_recent_backtest", now
        verdict = _forward_verdict(spec)
        if verdict == "approved" and spec.get("state") == "shadow":
            spec["state"], spec["approved_at"] = "approved", now
        elif verdict == "retired" and spec.get("state") != "retired":
            spec["state"], spec["retired_reason"], spec["retired_at"] = "retired", "negative_forward_record", now
    return sorted(by_id.values(), key=lambda s: (s["asset"], s["timeframe"], s["spec_id"]))


def _load_published() -> dict[str, Any]:
    try:
        from core.redis_state import state

        raw = state.get_sync(REDIS_KEY)
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def run_discovery(assets: list[str] | None = None, *, publish: bool = True,
                  timeframes: Iterable[str] = RESEARCH_TIMEFRAMES, use_stored: bool = False) -> dict[str, Any]:
    """``use_stored`` reads SignalRank's own candles when external history is short.

    Only the command line enables it: the analytics loop runs research in a
    worker thread, where the async database pool of the main loop is unusable.
    """
    import httpx

    rules = Rules.from_env()
    symbols = assets or default_universe()
    published = _load_published()
    existing = list(published.get("specs") or [])
    found: list[dict[str, Any]] = []
    rechecks: dict[str, dict[str, Any]] = {}
    report: list[dict[str, Any]] = []
    started = time.monotonic()
    with httpx.Client(headers=_HEADERS, timeout=30, follow_redirects=True) as client:
        for symbol in symbols:
            klass = asset_class(symbol)
            try:
                frames, source = load_history(symbol, klass, client)
            except Exception as exc:
                frames, source = {}, f"error:{type(exc).__name__}"
            for tf in timeframes:
                df = frames.get(tf)
                src = source
                if df is None or len(df) < 800:
                    stored = asyncio.run(stored_history(symbol, tf)) if use_stored and not _in_event_loop() else None
                    if stored is not None and len(stored) > (0 if df is None else len(df)):
                        df, src = stored, "signalrank"
                if df is None or df.empty:
                    report.append({"asset": symbol, "timeframe": tf, "skipped": "no_history"})
                    continue
                try:
                    result = research_frame(symbol, klass, tf, df, rules)
                except Exception as exc:
                    logger.warning("[discovery] research failed %s %s %s", symbol, tf, exc)
                    report.append({"asset": symbol, "timeframe": tf, "error": type(exc).__name__})
                    continue
                for s in result["survivors"]:
                    s["data_source"] = src
                found.extend(result["survivors"])
                for spec in existing:
                    if spec["asset"] == symbol and spec["timeframe"] == tf:
                        try:
                            rechecks[spec["spec_id"]] = recheck_spec(spec, df)
                        except Exception:
                            pass
                report.append({
                    "asset": symbol, "class": klass, "timeframe": tf, "source": src, "bars": result["bars"],
                    "configs": result["configs"], "passed_in_sample": result.get("passed_in_sample", 0),
                    "survivors": [
                        f"{s['family']} {s['direction']} {s['params']} stop={s['stop_atr']}ATR target={s['target_r']}R "
                        f"oos={s['metrics']['oos']['trades']}tr {s['metrics']['oos']['expectancy_r']:+.2f}R "
                        f"wr={s['metrics']['oos']['win_rate']}"
                        for s in result["survivors"]
                    ],
                    **({"skipped": result["skipped"]} if result.get("skipped") else {}),
                })
                logger.info("[discovery] %s %s source=%s bars=%s configs=%s survivors=%s", symbol, tf, src,
                            result["bars"], result["configs"], len(result["survivors"]))
    specs = merge_specs(existing, found, rechecks)
    summary = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "assets": len(symbols),
        "specs": len(specs),
        "states": {k: sum(1 for s in specs if s.get("state") == k) for k in ("shadow", "approved", "retired")},
        "new_this_run": len({s["spec_id"] for s in found} - {s["spec_id"] for s in existing}),
        "seconds": round(time.monotonic() - started, 1),
    }
    if publish:
        from core.redis_state import state

        state.set_sync(REDIS_KEY, json.dumps({"summary": summary, "specs": specs}, separators=(",", ":")))
    logger.info("[discovery] summary %s", json.dumps(summary))
    return {"summary": summary, "report": report, "specs": specs}


def _in_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


async def strategy_discovery_loop(stop: asyncio.Event) -> None:
    """Weekly re-discovery and re-validation on the analytics role."""
    interval = max(86400, _env_int("DISCOVERY_INTERVAL_SECONDS", 7 * 86400))
    delay = max(0, _env_int("DISCOVERY_STARTUP_DELAY_SECONDS", 1800))
    try:
        await asyncio.wait_for(stop.wait(), timeout=delay)
        return
    except asyncio.TimeoutError:
        pass
    while not stop.is_set():
        wait = interval
        try:
            # Research is CPU-bound and makes blocking HTTP calls: keep it off the loop.
            await asyncio.to_thread(run_discovery)
        except Exception as exc:
            wait = 6 * 3600
            logger.warning("[discovery] run failed error_type=%s error=%s", type(exc).__name__, str(exc)[:200])
        try:
            await asyncio.wait_for(stop.wait(), timeout=wait)
        except asyncio.TimeoutError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover per-asset strategies from long price history")
    parser.add_argument("--assets", default="", help="comma-separated symbols (default: TRADABLE_ASSETS)")
    parser.add_argument("--timeframes", default=",".join(RESEARCH_TIMEFRAMES))
    parser.add_argument("--dry-run", action="store_true", help="do not publish specs")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    assets = [a.strip().upper() for a in args.assets.split(",") if a.strip()] or None
    result = run_discovery(assets, publish=not args.dry_run, use_stored=True,
                           timeframes=[t.strip() for t in args.timeframes.split(",") if t.strip()])
    print(json.dumps(result["summary"], indent=2))
    for row in result["report"]:
        print(json.dumps(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
