"""Analyse a trade a user plans to take, track how it ends, and learn from it (10 Nov 2026).

Owner request: "add a feature where users can input the details of a trade they
want to take (asset, entry, TP and SL with every other detail); the bot analyses
it and tells them its possibility, and it also learns from those signals."

Analysis (``analyse``), all from market data the platform already reads:

* plan geometry: stop and targets on the right side, reward/risk per target and
  the break-even win rate ``1 / (1 + RR)``; the order type and pip/risk
  breakdown from ``engine/order_plan``;
* market context from recent candles: stop size in ATR (noise stops and very
  wide stops), distance of the entry from the current price, trend alignment
  (EMA 20/50), RSI 14 and recent momentum;
* **historical hit rate**: on this instrument and timeframe, from every recent
  bar, did price move the target distance before the stop distance? This is a
  model-free, explainable "how often has a move like this worked lately" with a
  Wilson 95 % lower bound; same-bar touches of both count as a loss;
* the engine's own recent record on the instrument, and how other users' ideas
  on it have ended (the learning loop below).

The probability shown is the historical TP1 hit rate (shrunk toward 50 % when
few samples exist); the verdict compares its lower bound with the break-even
rate the plan needs. Nothing here is advice or a guarantee; it says so.

Learning: each idea is stored in ``user_trade_ideas`` (0063). ``track_once``
waits for the entry to be touched, then labels the idea bar by bar with the same
rules as the shadow tracker (TP1 then stop to entry). The idea's owner is told
how it ended (notification centre, email/push per preferences, Telegram).
Resolved ideas feed the "ideas on this instrument" evidence shown to everyone
and join ML training as low-weight, fit-only rows (``ml/train_model``).
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import text

logger = logging.getLogger(__name__)

TIMEFRAMES = ("5m", "15m", "30m", "1h", "4h", "1d")
_WIN = ("tp1", "tp2", "tp3")


class IdeaError(ValueError):
    """The submitted idea cannot be analysed; the message is shown to the user."""


@dataclass
class Idea:
    asset: str
    direction: str
    entry: float
    stop_loss: float
    take_profit: list[float]
    timeframe: str = "1h"
    notes: str = ""


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


def _num(value: Any) -> Optional[float]:
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def normalise(raw: dict[str, Any]) -> Idea:
    """Validate a submitted idea (web form, API or parsed Telegram text)."""
    from services.asset_registry import normalize_symbol

    asset = normalize_symbol(str(raw.get("asset") or "").strip().upper().replace(" ", ""))
    if not asset:
        raise IdeaError("Add the instrument, e.g. EURUSD, XAUUSD or BTCUSDT.")
    direction = str(raw.get("direction") or "").strip().lower()
    direction = {"buy": "long", "long": "long", "sell": "short", "short": "short"}.get(direction, "")
    if not direction:
        raise IdeaError("Say whether it is a buy or a sell.")
    entry, stop = _num(raw.get("entry")), _num(raw.get("stop_loss") if raw.get("stop_loss") is not None else raw.get("sl"))
    if entry is None or stop is None:
        raise IdeaError("Add an entry price and a stop loss.")
    raw_tp = raw.get("take_profit") if raw.get("take_profit") is not None else raw.get("tp")
    if isinstance(raw_tp, str):
        raw_tp = [p for p in raw_tp.replace(",", " ").split() if p]
    targets = [t for t in (_num(t) for t in (raw_tp if isinstance(raw_tp, (list, tuple)) else [raw_tp])) if t][:3]
    if not targets:
        raise IdeaError("Add at least one take-profit price.")
    long_side = direction == "long"
    if (stop >= entry) if long_side else (stop <= entry):
        raise IdeaError(f"For a {'buy' if long_side else 'sell'}, the stop loss must be "
                        f"{'below' if long_side else 'above'} the entry.")
    bad = [t for t in targets if ((t <= entry) if long_side else (t >= entry))]
    if bad:
        raise IdeaError(f"For a {'buy' if long_side else 'sell'}, every take profit must be "
                        f"{'above' if long_side else 'below'} the entry.")
    targets = sorted(targets, reverse=not long_side)
    timeframe = str(raw.get("timeframe") or "1h").strip().lower()
    if timeframe not in TIMEFRAMES:
        raise IdeaError(f"Timeframe must be one of {', '.join(TIMEFRAMES)}.")
    return Idea(asset=asset, direction=direction, entry=entry, stop_loss=stop, take_profit=targets,
                timeframe=timeframe, notes=str(raw.get("notes") or "")[:500])


def parse_command_text(args: list[str]) -> dict[str, Any]:
    """``/check_trade EURUSD buy 1.0850 sl 1.0820 tp 1.0900 1.0950 tf 1h`` (any order after the side).

    Also accepts ``entry 1.0850``, ``@1.0850``, ``stop``/``sl``, ``tp``/``target``.
    """
    if len(args) < 2:
        raise IdeaError("Usage: /check_trade EURUSD buy 1.0850 sl 1.0820 tp 1.0900 1.0950 tf 1h")
    out: dict[str, Any] = {"asset": args[0], "direction": args[1], "take_profit": []}
    key = "entry"
    for token in args[2:]:
        word = token.strip().lower().lstrip("@")
        if word in {"entry", "at", "e"}:
            key = "entry"
        elif word in {"sl", "stop", "stoploss", "stop_loss"}:
            key = "stop_loss"
        elif word in {"tp", "tps", "target", "targets", "takeprofit", "take_profit"}:
            key = "take_profit"
        elif word in {"tf", "timeframe"}:
            key = "timeframe"
        elif key == "timeframe":
            out["timeframe"] = word
            key = "take_profit"
        elif key == "take_profit":
            out["take_profit"].append(word)
        else:
            out[key] = word
            if key == "entry":
                key = "stop_loss" if "stop_loss" not in out else "take_profit"
            elif key == "stop_loss":
                key = "take_profit"
    return out


# --------------------------------------------------------------------------- market maths

def _ohlc(candles: list[Any]) -> tuple[list[float], list[float], list[float]]:
    from core.atr_levels import ohlc

    return ohlc(candles)


def _ema(values: list[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    k = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return ema


def _rsi(closes: list[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains = losses = 0.0
    for i in range(len(closes) - period, len(closes)):
        change = closes[i] - closes[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100.0 - 100.0 / (1.0 + rs)


def wilson_lower(wins: int, n: int, z: float = 1.96) -> Optional[float]:
    if n <= 0:
        return None
    p = wins / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - margin) / denom)


def historical_hit_rate(highs: list[float], lows: list[float], closes: list[float], *, direction: str,
                        target_pct: float, stop_pct: float, horizon: int) -> dict[str, Any]:
    """From every past bar: target move before stop move within ``horizon`` bars?"""
    long_side = direction == "long"
    wins = losses = open_ = 0
    last_start = len(closes) - 2
    for start in range(0, max(0, last_start)):
        base = closes[start]
        if base <= 0:
            continue
        tp = base * (1 + target_pct) if long_side else base * (1 - target_pct)
        sl = base * (1 - stop_pct) if long_side else base * (1 + stop_pct)
        result = None
        for j in range(start + 1, min(len(closes), start + 1 + horizon)):
            hit_tp = highs[j] >= tp if long_side else lows[j] <= tp
            hit_sl = lows[j] <= sl if long_side else highs[j] >= sl
            if hit_sl:  # same-bar touches count as a loss (order inside the bar is unknown)
                result = "sl"
                break
            if hit_tp:
                result = "tp"
                break
        if result == "tp":
            wins += 1
        elif result == "sl":
            losses += 1
        else:
            open_ += 1
    decided = wins + losses
    return {"wins": wins, "losses": losses, "undecided": open_, "samples": decided,
            "rate": (wins / decided) if decided else None, "lower_95": wilson_lower(wins, decided)}


def _verdict(prob_lower: Optional[float], breakeven: float, warnings: list[str]) -> str:
    if prob_lower is None:
        return "unrated"
    edge = prob_lower - breakeven
    serious = sum(1 for w in warnings if w.startswith("!"))
    if edge >= 0.05 and serious == 0:
        return "favourable"
    if edge >= -0.05 and serious <= 1:
        return "marginal"
    return "unfavourable"


async def analyse(idea: Idea, *, candles: Optional[list[Any]] = None, session: Any = None) -> dict[str, Any]:
    """Everything the user is shown. ``candles`` may be injected (tests)."""
    from engine.order_plan import build_order_plan
    from services.asset_registry import classify_asset

    if candles is None:
        from data.fetcher import async_get_candles

        try:
            candles = await asyncio.wait_for(async_get_candles(idea.asset, idea.timeframe), timeout=20.0)
        except Exception:
            candles = []
    highs, lows, closes = _ohlc(list(candles or []))
    if len(closes) < 60:
        raise IdeaError(f"Not enough recent {idea.timeframe} price data for {idea.asset} to analyse it. "
                        "Check the symbol, or try another timeframe.")
    from core.atr_levels import atr

    price = closes[-1]
    atr_value = atr(highs, lows, closes) or 0.0
    risk = abs(idea.entry - idea.stop_loss)
    long_side = idea.direction == "long"
    rr = [abs(t - idea.entry) / risk for t in idea.take_profit]
    breakeven = 1.0 / (1.0 + rr[0])
    warnings: list[str] = []
    notes: list[str] = []

    stop_atr = risk / atr_value if atr_value else None
    if stop_atr is not None:
        if stop_atr < 0.5:
            warnings.append(f"! Stop is only {stop_atr:.2f} ATR away: normal {idea.timeframe} noise can hit it.")
        elif stop_atr > 4:
            warnings.append(f"Stop is {stop_atr:.1f} ATR away: very wide for {idea.timeframe}; size down.")
        else:
            notes.append(f"Stop is {stop_atr:.2f} ATR away.")
    entry_atr = abs(idea.entry - price) / atr_value if atr_value else None
    if entry_atr is not None and entry_atr > 3:
        warnings.append(f"Entry is {entry_atr:.1f} ATR from the current price: it may not fill soon.")
    if rr[0] < 1:
        warnings.append(f"! TP1 pays {rr[0]:.2f}R: you need to win more than {breakeven:.0%} of the time.")
    if (long_side and price <= idea.stop_loss) or (not long_side and price >= idea.stop_loss):
        warnings.append("! Price is already beyond your stop loss.")

    ema20, ema50 = _ema(closes, 20), _ema(closes, 50)
    trend = 0
    if ema20 and ema50:
        trend = 1 if (price > ema20 > ema50) else -1 if (price < ema20 < ema50) else 0
    aligned = (trend == 1 and long_side) or (trend == -1 and not long_side)
    against = (trend == -1 and long_side) or (trend == 1 and not long_side)
    if aligned:
        notes.append(f"With the {idea.timeframe} trend (price and EMA20 above/below EMA50).")
    elif against:
        warnings.append(f"! Against the {idea.timeframe} trend (EMA20/EMA50).")
    else:
        notes.append(f"No clear {idea.timeframe} trend.")
    rsi = _rsi(closes)
    if rsi is not None:
        if long_side and rsi >= 75:
            warnings.append(f"RSI {rsi:.0f}: stretched for a buy.")
        elif not long_side and rsi <= 25:
            warnings.append(f"RSI {rsi:.0f}: stretched for a sell.")
    momentum = (closes[-1] / closes[-11] - 1.0) if len(closes) > 11 and closes[-11] > 0 else 0.0

    horizon = max(10, _env_int("IDEA_HIT_RATE_HORIZON_BARS", 48))
    stop_pct = risk / idea.entry
    hit = [historical_hit_rate(highs, lows, closes, direction=idea.direction,
                               target_pct=abs(t - idea.entry) / idea.entry, stop_pct=stop_pct, horizon=horizon)
           for t in idea.take_profit]
    tp1 = hit[0]
    probability = None
    if tp1["rate"] is not None:
        n = tp1["samples"]
        prior_n = 20.0  # shrink toward 50 % when the sample is small
        probability = (tp1["wins"] + 0.5 * prior_n) / (n + prior_n)
    verdict = _verdict(tp1["lower_95"], breakeven, warnings)

    evidence: dict[str, Any] = {}
    if session is not None:
        try:
            evidence = await _evidence(session, idea.asset)
        except Exception as exc:
            logger.info("[trade_ideas] evidence unavailable asset=%s error=%s", idea.asset, type(exc).__name__)

    plan = build_order_plan({"asset": idea.asset, "direction": idea.direction, "entry": idea.entry,
                             "stop_loss": idea.stop_loss, "take_profit": idea.take_profit, "current_price": price})
    atr_rel = (atr_value / price) if price else 0.0
    features = {
        "atr_rel": round(atr_rel, 6), "rsi": None if rsi is None else round(rsi, 2), "trend": trend,
        "price_velocity_10": round(momentum, 6), "stop_atr": None if stop_atr is None else round(stop_atr, 4),
        "entry_atr": None if entry_atr is None else round(entry_atr, 4), "rr_ratio": round(rr[0], 4),
        "hist_tp1_rate": tp1["rate"], "hist_samples": tp1["samples"],
    }
    return {
        "asset": idea.asset,
        "asset_class": classify_asset(idea.asset),
        "direction": idea.direction,
        "timeframe": idea.timeframe,
        "entry": idea.entry,
        "stop_loss": idea.stop_loss,
        "take_profit": idea.take_profit,
        "current_price": price,
        "risk_reward": [round(r, 2) for r in rr],
        "breakeven_win_rate": round(breakeven, 4),
        "probability_tp1": None if probability is None else round(probability, 4),
        "historical": [{"target": i + 1, **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in h.items()}}
                       for i, h in enumerate(hit)],
        "horizon_bars": horizon,
        "verdict": verdict,
        "warnings": [w.lstrip("! ") for w in warnings],
        "notes": notes,
        "order_plan": plan,
        "evidence": evidence,
        "features": features,
        "disclaimer": "An estimate from recent price history, not advice or a guarantee. Markets change; size so a loss is affordable.",
    }


async def _evidence(session: Any, asset: str) -> dict[str, Any]:
    engine = (await session.execute(text(
        "SELECT COUNT(*) AS closed, COUNT(*) FILTER (WHERE lower(COALESCE(o.canonical_outcome,o.status,'')) "
        "IN ('tp','tp1','tp2','tp3','partial_tp','win','partial_win')) AS hit_tp1, AVG(o.r_multiple) AS avg_r "
        "FROM outcomes o JOIN signals s ON s.signal_id=o.signal_id WHERE s.asset=:a "
        "AND o.closed_at >= (NOW() AT TIME ZONE 'utc') - INTERVAL '60 days' AND o.r_multiple IS NOT NULL"),
        {"a": asset})).mappings().one()
    ideas = (await session.execute(text(
        "SELECT COUNT(*) AS resolved, COUNT(*) FILTER (WHERE outcome IN ('tp1','tp2','tp3')) AS hit_tp1 "
        "FROM user_trade_ideas WHERE asset=:a AND resolved_at >= (NOW() AT TIME ZONE 'utc') - INTERVAL '90 days' "
        "AND outcome IN ('tp1','tp2','tp3','sl')"), {"a": asset})).mappings().one()
    return {
        "engine_closed_60d": int(engine["closed"] or 0),
        "engine_tp1_rate_60d": (int(engine["hit_tp1"] or 0) / int(engine["closed"])) if engine["closed"] else None,
        "engine_avg_r_60d": None if engine["avg_r"] is None else round(float(engine["avg_r"]), 3),
        "ideas_resolved_90d": int(ideas["resolved"] or 0),
        "ideas_tp1_rate_90d": (int(ideas["hit_tp1"] or 0) / int(ideas["resolved"])) if ideas["resolved"] else None,
    }


# --------------------------------------------------------------------------- storage

def daily_limit(tier: str) -> int:
    defaults = {"free": 3, "premium": 20, "vip": 100, "professional": 100, "institutional": 500,
                "admin": 1000, "owner": 1000}
    tier = str(tier or "free").lower()
    return max(0, _env_int(f"IDEA_DAILY_LIMIT_{tier.upper()}", defaults.get(tier, 3)))


async def used_today(session: Any, user_id: int) -> int:
    return int((await session.execute(text(
        "SELECT COUNT(*) FROM user_trade_ideas WHERE user_id=:u "
        "AND created_at >= date_trunc('day', NOW() AT TIME ZONE 'utc')"), {"u": int(user_id)})).scalar() or 0)


async def submit(session: Any, *, user_id: int, tier: str, raw: dict[str, Any], source: str,
                 candles: Optional[list[Any]] = None) -> dict[str, Any]:
    """Validate, enforce the tier's daily limit, analyse, store; returns the analysis with ``idea_id``."""
    idea = normalise(raw)
    limit = daily_limit(tier)
    if await used_today(session, user_id) >= limit:
        raise IdeaError(f"You have used today's {limit} trade analyses on your plan. /upgrade for more.")
    result = await analyse(idea, candles=candles, session=session)
    idea_id = str(uuid4())
    await session.execute(text(
        "INSERT INTO user_trade_ideas(idea_id,user_id,asset,asset_class,timeframe,direction,order_type,entry,stop_loss,"
        "take_profit,price_at_submit,probability,verdict,analysis,features,source,notes) VALUES "
        "(:i,:u,:a,:c,:tf,:d,:ot,:e,:sl,CAST(:tp AS JSONB),:p,:prob,:v,CAST(:an AS JSONB),CAST(:f AS JSONB),:src,:n)"),
        {"i": idea_id, "u": int(user_id), "a": idea.asset, "c": str(result.get("asset_class") or "")[:16],
         "tf": idea.timeframe, "d": idea.direction,
         "ot": str(((result.get("order_plan") or {}).get("order") or {}).get("type") or "")[:32],
         "e": idea.entry, "sl": idea.stop_loss, "tp": json.dumps(idea.take_profit), "p": result["current_price"],
         "prob": result.get("probability_tp1"), "v": result["verdict"],
         "an": json.dumps({k: v for k, v in result.items() if k != "features"}, default=str),
         "f": json.dumps(result["features"], default=str), "src": str(source)[:16], "n": idea.notes or None})
    return {**result, "idea_id": idea_id, "used_today": await used_today(session, user_id), "daily_limit": limit}


async def history(session: Any, user_id: int, limit: int = 30) -> dict[str, Any]:
    rows = (await session.execute(text(
        "SELECT idea_id, asset, timeframe, direction, entry, stop_loss, take_profit, probability, verdict, status, "
        "outcome, outcome_r, created_at, resolved_at, source FROM user_trade_ideas WHERE user_id=:u "
        "ORDER BY created_at DESC LIMIT :n"), {"u": int(user_id), "n": int(limit)})).mappings().all()
    items = [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in dict(r).items()} for r in rows]
    resolved = [i for i in items if i["outcome"] in ("tp1", "tp2", "tp3", "sl")]
    wins = sum(1 for i in resolved if i["outcome"] in _WIN)
    return {"ideas": items, "resolved": len(resolved), "tp1_or_better": wins,
            "hit_rate": (wins / len(resolved)) if resolved else None}


# --------------------------------------------------------------------------- tracking + notifying

def label_idea(row: dict[str, Any], candles: list[Any], *, expiry_bars: int) -> tuple[Optional[str], Optional[datetime]]:
    """(outcome, entry_touched_at). Waits for the entry, then labels like the shadow tracker."""
    from engine.shadow_outcome_worker import _candle_time, _candle_value, _timeframe_seconds, label_from_candles

    created = row["created_at"]
    if isinstance(created, datetime) and created.tzinfo is not None:
        created = created.astimezone(timezone.utc).replace(tzinfo=None)
    long_side = str(row["direction"]) == "long"
    entry = float(row["entry"])
    price0 = float(row.get("price_at_submit") or entry)
    band = abs(entry - float(row["stop_loss"])) * 0.1
    touched = row.get("entry_touched_at")
    after = [c for c in candles if (_candle_time(c) or datetime.min) >= created]
    if touched is None:
        if abs(price0 - entry) <= band:
            touched = created
        else:
            for c in after:
                hi, lo = _candle_value(c, "high", "h"), _candle_value(c, "low", "l")
                if hi is not None and lo is not None and lo <= entry <= hi:
                    touched = _candle_time(c)
                    break
    if touched is None:
        bar = timedelta(seconds=_timeframe_seconds(row.get("timeframe")))
        if datetime.now(timezone.utc).replace(tzinfo=None) - created > bar * expiry_bars:
            return "missed_entry", None
        return None, None
    tps = row["take_profit"] if isinstance(row["take_profit"], list) else json.loads(row["take_profit"] or "[]")
    outcome = label_from_candles({"direction": "long" if long_side else "short", "entry": entry,
                                  "stop_loss": row["stop_loss"], "take_profit": tps, "created_at": touched,
                                  "timeframe": row.get("timeframe")}, candles)
    if outcome is None:
        bar = timedelta(seconds=_timeframe_seconds(row.get("timeframe")))
        if datetime.now(timezone.utc).replace(tzinfo=None) - touched > bar * expiry_bars * 2:
            # Out of time with no stop: credit the highest target reached (the plan banked it).
            reached = 0
            for c in candles:
                if (_candle_time(c) or datetime.min) < touched:
                    continue
                hi, lo = _candle_value(c, "high", "h"), _candle_value(c, "low", "l")
                for index, target in enumerate(float(t) for t in tps):
                    if (hi is not None and hi >= target) if long_side else (lo is not None and lo <= target):
                        reached = max(reached, index + 1)
            return (f"tp{reached}" if reached else "expired"), touched
        return None, touched
    return outcome, touched  # tp1/tp2/tp3/sl, or "ambiguous" (target and stop in one bar: final, no result)


def outcome_r(row: dict[str, Any], outcome: str) -> Optional[float]:
    """R of the published plan: 50 % at TP1, 25 % at TP2, rest at TP3; stop to entry after TP1."""
    if outcome == "sl":
        return -1.0
    tps = row["take_profit"] if isinstance(row["take_profit"], list) else json.loads(row["take_profit"] or "[]")
    risk = abs(float(row["entry"]) - float(row["stop_loss"]))
    if not risk or outcome not in _WIN:
        return None  # missed entry, expired or ambiguous: no trade result
    rr = [abs(float(t) - float(row["entry"])) / risk for t in tps]
    level = int(outcome[-1])
    if len(rr) == 1:
        return round(rr[0], 3)
    weights = [0.5, 0.25, 0.25][: len(rr)]
    total = sum(weights[i] * rr[i] for i in range(min(level, len(rr))))
    return round(total, 3)  # the rest closed at entry (0R)


async def track_once(*, candle_fetch=None) -> dict[str, int]:
    from db.session import get_session

    expiry_bars = max(6, _env_int("IDEA_ENTRY_EXPIRY_BARS", 48))
    async with get_session(priority="analytics", label="trade_ideas.track", timeout_seconds=15.0) as session:
        rows = [dict(r) for r in (await session.execute(text(
            "SELECT id, idea_id, user_id, asset, timeframe, direction, entry, stop_loss, take_profit, price_at_submit, "
            "entry_touched_at, created_at FROM user_trade_ideas WHERE status='tracking' ORDER BY id LIMIT 200"
        ))).mappings().all()]
        await session.rollback()
    if not rows:
        return {"checked": 0, "resolved": 0}
    fetch = candle_fetch
    if fetch is None:
        from data.fetcher import async_get_candles

        fetch = async_get_candles
    series: dict[tuple[str, str], list[Any]] = {}
    for key in {(r["asset"], r["timeframe"]) for r in rows}:
        try:
            series[key] = list(await asyncio.wait_for(fetch(*key), timeout=20.0) or [])
        except Exception:
            series[key] = []
    resolved = 0
    async with get_session(priority="analytics", label="trade_ideas.track_write", timeout_seconds=15.0) as session:
        for row in rows:
            candles = series.get((row["asset"], row["timeframe"])) or []
            if not candles:
                continue
            outcome, touched = label_idea(row, candles, expiry_bars=expiry_bars)
            if touched and not row.get("entry_touched_at"):
                await session.execute(text("UPDATE user_trade_ideas SET entry_touched_at=:t, updated_at=NOW() "
                                           "WHERE id=:id"), {"t": touched, "id": row["id"]})
            if outcome:
                await session.execute(text(
                    "UPDATE user_trade_ideas SET status='resolved', outcome=:o, outcome_r=:r, "
                    "resolved_at=(NOW() AT TIME ZONE 'utc'), updated_at=NOW() WHERE id=:id AND status='tracking'"),
                    {"o": outcome, "r": outcome_r(row, outcome), "id": row["id"]})
                resolved += 1
        await session.commit()
    return {"checked": len(rows), "resolved": resolved}


def outcome_text(row: dict[str, Any]) -> tuple[str, str]:
    side = "BUY" if row["direction"] == "long" else "SELL"
    label = {"tp1": "reached TP1", "tp2": "reached TP2", "tp3": "reached the final target", "sl": "hit the stop loss",
             "missed_entry": "never reached your entry", "expired": "ran out of time without a result",
             "ambiguous": "touched a target and the stop in the same bar (no result)"}.get(str(row["outcome"]),
                                                                                         str(row["outcome"]))
    r = row.get("outcome_r")
    r_text = "" if r is None else f" ({float(r):+.2f}R by the 50/25/25 plan)"
    prob = row.get("probability")
    p_text = "" if prob is None else f" The analysis gave TP1 {float(prob) * 100:.0f}%."
    title = f"Your {row['asset']} idea {label}"
    body = (f"📒 Your {row['asset']} {side} idea ({row['timeframe']}) {label}{r_text}.{p_text} "
            "Every resolved idea improves the analysis for everyone. See all yours: /my_ideas")
    return title, body


async def notify_once(*, telegram_post=None) -> int:
    from db.session import get_session

    sent: list[tuple[Optional[int], str]] = []
    async with get_session(priority="analytics", label="trade_ideas.notify", timeout_seconds=15.0) as session:
        rows = [dict(r) for r in (await session.execute(text(
            "SELECT i.id, i.idea_id, i.user_id, i.asset, i.timeframe, i.direction, i.outcome, i.outcome_r, "
            "i.probability, u.telegram_user_id FROM user_trade_ideas i JOIN users u ON u.id=i.user_id "
            "WHERE i.status='resolved' AND i.notified_at IS NULL ORDER BY i.id LIMIT 100"))).mappings().all()]
        for row in rows:
            title, body = outcome_text(row)
            await session.execute(text(
                "INSERT INTO notification_events(notification_id,user_id,event_type,title,body,severity,channel_data,"
                "created_at) VALUES (:nid,:uid,'alert',:t,:b,'info',CAST(:d AS JSONB),NOW()) "
                "ON CONFLICT(notification_id) DO NOTHING"),
                {"nid": row["idea_id"], "uid": int(row["user_id"]), "t": title[:200], "b": body,
                 "d": json.dumps({"kind": "trade_idea_outcome", "idea_id": row["idea_id"], "url": "/app/analyze"})})
            await session.execute(text("UPDATE user_trade_ideas SET notified_at=(NOW() AT TIME ZONE 'utc') WHERE id=:id"),
                                  {"id": row["id"]})
            sent.append((row.get("telegram_user_id"), body))
        await session.commit()
    if sent and str(os.getenv("IDEA_TELEGRAM_DM", "1")).lower() in {"1", "true", "yes", "on"}:
        from services.weekly_scorecard import _telegram_post

        post = telegram_post or _telegram_post
        for chat, body in sent:
            if chat:
                try:
                    await post(int(chat), body)
                except Exception:
                    pass
                await asyncio.sleep(0.05)
    return len(sent)


async def trade_ideas_loop(stop: asyncio.Event) -> None:
    interval = max(30, _env_int("IDEA_TRACK_INTERVAL_SECONDS", 120))
    while not stop.is_set():
        try:
            await track_once()
            await notify_once()
        except Exception as exc:
            logger.warning("[trade_ideas] pass failed error=%s", type(exc).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue


# --------------------------------------------------------------------------- presentation

def telegram_text(result: dict[str, Any]) -> str:
    side = "BUY" if result["direction"] == "long" else "SELL"
    verdict = {"favourable": "🟢 Favourable", "marginal": "🟡 Marginal", "unfavourable": "🔴 Unfavourable",
               "unrated": "⚪ Not enough history"}.get(result["verdict"], result["verdict"])
    prob = result.get("probability_tp1")
    lines = [f"🔍 Trade analysis: {result['asset']} {side} ({result['timeframe']})", "",
             f"Verdict: {verdict}"]
    if prob is not None:
        lines.append(f"Chance of TP1 before the stop (recent history): {prob * 100:.0f}%")
    lines.append(f"Break-even win rate for TP1 at {result['risk_reward'][0]:.2f}R: {result['breakeven_win_rate'] * 100:.0f}%")
    for h in result["historical"]:
        if h.get("rate") is not None:
            lines.append(f"• TP{h['target']}: {h['rate'] * 100:.0f}% of {h['samples']} similar moves "
                         f"(worst case {(h.get('lower_95') or 0) * 100:.0f}%) within {result['horizon_bars']} bars")
    lines.append(f"Price now: {result['current_price']:,.6g} • R/R " + " / ".join(f"{r:.2f}" for r in result["risk_reward"]))
    for w in result["warnings"]:
        lines.append(f"⚠️ {w}")
    for n in result["notes"]:
        lines.append(f"• {n}")
    ev = result.get("evidence") or {}
    if ev.get("engine_closed_60d"):
        lines.append(f"📊 SignalRank signals on {result['asset']}, 60 days: {ev['engine_closed_60d']} closed, "
                     f"TP1 {((ev.get('engine_tp1_rate_60d') or 0) * 100):.0f}%")
    if ev.get("ideas_resolved_90d"):
        lines.append(f"👥 Users' ideas on {result['asset']}, 90 days: {ev['ideas_resolved_90d']} resolved, "
                     f"TP1 {((ev.get('ideas_tp1_rate_90d') or 0) * 100):.0f}%")
    try:
        from engine.order_plan import order_plan_lines

        lines += order_plan_lines({"asset": result["asset"], "direction": result["direction"], "entry": result["entry"],
                                   "stop_loss": result["stop_loss"], "take_profit": result["take_profit"],
                                   "current_price": result["current_price"]})
    except Exception:
        pass
    if result.get("idea_id"):
        lines.append(f"\n📒 Saved and tracked: you will get a message when it ends. "
                     f"{result.get('used_today')}/{result.get('daily_limit')} analyses used today. /my_ideas")
    lines.append(f"\n{result['disclaimer']}")
    return "\n".join(lines)
