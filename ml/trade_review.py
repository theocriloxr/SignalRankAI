"""Trade reviews and lessons: why a trade worked, what hurt it, and what to change (23 Nov 2026).

Every resolved setup the bot has tracked (delivered signals, paper trades, tracked rejected
setups, archived proof, user ideas) is reviewed against the same context factors:

* when: trading session, minutes to/from a high-impact release;
* where: with or against the 4h and daily trend, ADX trend strength, relative volume, volatility;
* how: strategy, timeframe, direction, TP1 reward/risk.

``build_snapshot`` turns the resolved history into a factor table: for each factor value, its
trades, win rate and realised R at TP1 (a loss is -1R), compared with every other trade of the
same asset class. A factor is only called a lesson when the difference survives a
Benjamini-Hochberg false-discovery correction across all the factors tested, so the many
comparisons cannot invent lessons from noise.

``review_trade`` answers, for one trade: what made it work (factors present with a measured
positive edge), what hurt it (factors with a measured negative edge), whether its setup type is
improving or getting worse lately, and the concrete change that the evidence supports.

Self-improvement is tighten-only and evidence-gated (``harmful_lesson``): a context that loses
money with high confidence inside an asset class (corrected q <= 0.05, at least 50 trades,
upper 95 % bound of its mean R below 0) rejects new setups in that context. Rejected setups
keep being tracked, so a lesson that stops being true drops out at the next snapshot. Nothing
here loosens a gate; the ML gates and the forward proof are unchanged.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Iterable

SNAPSHOT_KEY = "learning:trade_review"
MIN_TRADES = 30
GATE_MIN_TRADES = 50
LESSON_Q = 0.10
GATE_Q = 0.05

# Factors a gate may act on: context (when/where), never a whole asset, class or strategy.
GATE_FACTORS = {"session", "trend_4h", "trend_1d", "trend_strength", "volume", "volatility", "news", "reward"}

_ADVICE = {
    ("trend_4h", "against"): "take it only in the direction of the 4h trend",
    ("trend_1d", "against"): "take it only in the direction of the daily trend",
    ("trend_strength", "weak"): "skip it when ADX is below 20 (no trend to ride)",
    ("volume", "low"): "wait for volume to come back above its average",
    ("volatility", "high"): "use a wider stop and smaller size, or wait for volatility to settle",
    ("volatility", "low"): "skip it in very quiet markets; targets rarely get reached",
    ("news", "before_release"): "wait until the high-impact release is out",
    ("news", "after_release"): "wait for the first post-release candle to close before entering",
    ("reward", "far"): "use a nearer first target (TP1 under 2.5R)",
    ("reward", "near"): "the target is too close for the risk; look for at least 1.5R",
}

_LABELS = {
    "session": "session", "trend_4h": "4h trend", "trend_1d": "daily trend", "trend_strength": "ADX",
    "volume": "volume", "volatility": "volatility", "news": "news", "reward": "TP1 reward",
    "strategy": "strategy", "timeframe": "timeframe", "direction": "direction", "regime": "regime",
}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except (TypeError, ValueError):
        return default


def asset_class(asset: str) -> str:
    try:
        from services.asset_mapper import classify_asset

        return str(classify_asset(str(asset or "")) or "other").lower()
    except Exception:
        return "crypto" if str(asset or "").upper().endswith("USDT") else "other"


def excluded_sources() -> set[str]:
    """Sources left out of lessons (24 Nov 2026): ``archive_legacy`` is old signal history with no
    delivery proof and was ~70 % of a 365-day review, so it drove lessons and the gate."""
    import os

    raw = os.getenv("TRADE_REVIEW_EXCLUDED_SOURCES", "archive_legacy")
    return {s.strip() for s in raw.split(",") if s.strip()}


def realised_r(row: dict[str, Any]) -> float | None:
    """TP1 outcome in R: +reward on a win, -1 on a loss, None when unresolved."""
    target = row.get("target")
    if target is None or (isinstance(target, float) and math.isnan(target)):
        return None
    entry, stop, tp = _f(row.get("entry")), _f(row.get("stop_loss")), _f(row.get("take_profit"))
    risk = abs(entry - stop)
    reward = abs(tp - entry) / risk if risk > 0 and tp > 0 else _f(row.get("rr_ratio"), 2.0) or 2.0
    reward = min(10.0, max(0.2, reward))
    return reward if int(_f(target)) == 1 else -1.0


def _session(ts: Any) -> str | None:
    try:
        import pandas as pd

        stamp = pd.Timestamp(ts)
        if pd.isna(stamp):
            return None
        hour = (stamp.tz_convert("UTC") if stamp.tzinfo else stamp).hour
    except Exception:
        return None
    if hour < 7:
        return "asia"
    if hour < 12:
        return "london"
    if hour < 16:
        return "london_newyork_overlap"
    if hour < 21:
        return "newyork"
    return "late_us"


def factors(row: dict[str, Any]) -> dict[str, str]:
    """The context factor values of one setup (missing context is left out, not guessed)."""
    out: dict[str, str] = {}
    direction = str(row.get("direction") or "").lower()
    sign = 1.0 if direction in {"long", "buy"} else -1.0 if direction in {"short", "sell"} else 0.0
    for key in ("strategy_name", "timeframe", "regime"):
        value = str(row.get(key) or "").strip()
        if key != "strategy_name":
            value = value.lower()  # 24 Nov 2026: "TRENDING" and "trending" were split into two factors
        if value and value.lower() not in {"unknown", "rejected", "nan", "none"}:
            out["strategy" if key == "strategy_name" else key] = value
    if sign:
        out["direction"] = "long" if sign > 0 else "short"
    session = _session(row.get("created_at"))
    if session:
        out["session"] = session
    for key, name in (("mtf_4h_trend", "trend_4h"), ("mtf_1d_trend", "trend_1d")):
        trend = _f(row.get(key))
        if trend and sign:
            out[name] = "with" if trend * sign > 0 else "against"
    adx = _f(row.get("adx"))
    if adx > 0:
        out["trend_strength"] = "weak" if adx < 20 else "strong" if adx > 35 else "trending"
    volume = _f(row.get("relative_volume"))
    if volume > 0:
        out["volume"] = "low" if volume < 0.7 else "high" if volume > 1.5 else "normal"
    vol = _f(row.get("atr_regime"))
    if vol > 0:
        out["volatility"] = "low" if vol < 0.8 else "high" if vol > 1.3 else "normal"
    until, since = _f(row.get("minutes_until_high_impact_news")), _f(row.get("minutes_since_high_impact_news"))
    if 0 < until <= 60:
        out["news"] = "before_release"
    elif 0 < since <= 60:
        out["news"] = "after_release"
    elif until > 0 or since > 0:
        out["news"] = "clear"
    r = realised_r({**row, "target": 1})
    if r is not None:
        out["reward"] = "near" if r < 1.5 else "far" if r > 2.5 else "standard"
    return out


def _p_two_sided(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2.0))


def _stats(values: list[float]) -> tuple[float, float]:
    n = len(values)
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1) if n > 1 else 0.0
    return mean, var


def _bh(pvalues: list[float]) -> list[float]:
    """Benjamini-Hochberg adjusted q-values, same order as the input."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    q = [1.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, pvalues[i] * m / rank)
        q[i] = min(1.0, running)
    return q


def factor_table(rows: Iterable[dict[str, Any]], *, min_trades: int = MIN_TRADES) -> list[dict[str, Any]]:
    """Per (asset class, factor, value): trades, win rate, mean R, edge vs the rest of the class, q-value."""
    by_class: dict[str, list[tuple[dict[str, str], float, int]]] = {}
    for row in rows:
        r = realised_r(row)
        if r is None:
            continue
        cls = asset_class(str(row.get("asset") or ""))
        by_class.setdefault(cls, []).append((factors(row), r, 1 if r > 0 else 0))
        by_class.setdefault("all", []).append((factors(row), r, 1 if r > 0 else 0))
    table: list[dict[str, Any]] = []
    for cls, items in by_class.items():
        keys = {(k, v) for fac, _r, _w in items for k, v in fac.items()}
        for key, value in keys:
            inside = [r for fac, r, _w in items if fac.get(key) == value]
            outside = [r for fac, r, _w in items if key in fac and fac.get(key) != value]
            if len(inside) < min_trades or len(outside) < min_trades:
                continue
            m_in, v_in = _stats(inside)
            m_out, v_out = _stats(outside)
            se = math.sqrt(v_in / len(inside) + v_out / len(outside)) or 1e-9
            se_in = math.sqrt(v_in / len(inside)) if len(inside) > 1 else 0.0
            table.append({
                "asset_class": cls, "factor": key, "value": value, "trades": len(inside),
                "win_rate": round(sum(1 for r in inside if r > 0) / len(inside), 4),
                "mean_r": round(m_in, 4), "rest_mean_r": round(m_out, 4), "edge_r": round(m_in - m_out, 4),
                "mean_r_upper95": round(m_in + 1.96 * se_in, 4), "mean_r_lower95": round(m_in - 1.96 * se_in, 4),
                "p": _p_two_sided((m_in - m_out) / se),
            })
    for row, q in zip(table, _bh([t["p"] for t in table])):
        row["q"] = round(q, 5)
        row["p"] = round(row["p"], 6)
    table.sort(key=lambda t: (t["asset_class"], t["q"], -abs(t["edge_r"])))
    return table


def _trend(rows: list[dict[str, Any]], *, now: datetime, recent_days: int = 30) -> list[dict[str, Any]]:
    """Is each (class, strategy, timeframe) setup type getting better or worse lately?"""
    import pandas as pd

    groups: dict[tuple[str, str, str], dict[str, list[float]]] = {}
    cutoff = pd.Timestamp(now).tz_localize(None) - pd.Timedelta(days=recent_days)
    for row in rows:
        r = realised_r(row)
        stamp = pd.to_datetime(row.get("created_at"), errors="coerce")
        if r is None or pd.isna(stamp):
            continue
        stamp = stamp.tz_convert(None) if stamp.tzinfo else stamp
        key = (asset_class(str(row.get("asset") or "")), str(row.get("strategy_name") or "?"),
               str(row.get("timeframe") or "?"))
        groups.setdefault(key, {"recent": [], "before": []})["recent" if stamp >= cutoff else "before"].append(r)
    out = []
    for (cls, strategy, tf), parts in groups.items():
        if len(parts["recent"]) < 20 or len(parts["before"]) < 20:
            continue
        m_r, v_r = _stats(parts["recent"])
        m_b, v_b = _stats(parts["before"])
        se = math.sqrt(v_r / len(parts["recent"]) + v_b / len(parts["before"])) or 1e-9
        out.append({"asset_class": cls, "strategy": strategy, "timeframe": tf,
                    "recent_trades": len(parts["recent"]), "recent_mean_r": round(m_r, 4),
                    "before_trades": len(parts["before"]), "before_mean_r": round(m_b, 4),
                    "change_r": round(m_r - m_b, 4), "p": _p_two_sided((m_r - m_b) / se)})
    for row, q in zip(out, _bh([t["p"] for t in out])):
        row["q"] = round(q, 5)
        row["p"] = round(row["p"], 6)
        row["direction"] = ("improving" if row["change_r"] > 0 else "worsening") if q <= LESSON_Q else "steady"
    out.sort(key=lambda t: (t["q"], -abs(t["change_r"])))
    return out


def lesson_text(entry: dict[str, Any]) -> str:
    label = _LABELS.get(entry["factor"], entry["factor"])
    cls = "all assets" if entry["asset_class"] == "all" else entry["asset_class"]
    verb = "helps" if entry["edge_r"] > 0 else "hurts"
    text = (f"{cls}: {label} = {entry['value'].replace('_', ' ')} {verb} "
            f"({entry['mean_r']:+.2f}R per trade vs {entry['rest_mean_r']:+.2f}R otherwise, "
            f"win rate {entry['win_rate']:.0%}, {entry['trades']} trades)")
    advice = _ADVICE.get((entry["factor"], entry["value"]))
    if entry["edge_r"] < 0 and advice:
        text += f"; next time: {advice}"
    return text


def build_snapshot(rows: list[dict[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    resolved = [r for r in rows if realised_r(r) is not None]
    table = factor_table(resolved)
    lessons = [t for t in table if t["q"] <= LESSON_Q]
    harmful = [t for t in table if is_harmful(t)]
    rs = [realised_r(r) for r in resolved]
    trends = _trend(resolved, now=now)
    return {
        "generated_at": now.isoformat(),
        "resolved_trades": len(resolved),
        "overall": {"win_rate": round(sum(1 for r in rs if r and r > 0) / len(rs), 4) if rs else None,
                    "mean_r": round(sum(rs) / len(rs), 4) if rs else None},
        "by_class": _class_summary(resolved),
        "factors": table,
        "lessons": [{**t, "text": lesson_text(t)} for t in lessons],
        "harmful": [{**t, "text": lesson_text(t)} for t in harmful],
        "trends": trends,
        "reviews": _recent_reviews(resolved, {"factors": table, "trends": trends}),
        "method": {"min_trades": MIN_TRADES, "lesson_q": LESSON_Q, "gate_q": GATE_Q,
                   "gate_min_trades": GATE_MIN_TRADES, "correction": "benjamini_hochberg"},
    }


REVIEWED_SOURCES = {"live_delivery", "paper_execution", "archive_proof", "archive_legacy"}


def _recent_reviews(rows: list[dict[str, Any]], snap: dict[str, Any], *,
                    limit: int = 400) -> dict[str, dict[str, Any]]:
    """Stored reviews of the latest delivered/paper trades, keyed by signal id (for /why and the API)."""
    import pandas as pd

    picked = [r for r in rows if str(r.get("source_type") or "") in REVIEWED_SOURCES and r.get("signal_id")]
    def _stamp(row: dict[str, Any]) -> float:
        value = pd.to_datetime(row.get("created_at"), errors="coerce")
        return 0.0 if pd.isna(value) else float(value.timestamp())

    picked.sort(key=_stamp, reverse=True)
    out = {}
    for row in picked[:limit]:
        review = review_trade(row, snap)
        out[str(row["signal_id"])] = {"text": review_text(review), "headline": review["headline"],
                                      "why": review["why"], "improve": review["improve"],
                                      "factors": review["factors"], "realised_r": review["realised_r"],
                                      "asset": row.get("asset"), "timeframe": row.get("timeframe"),
                                      "created_at": str(row.get("created_at"))}
    return out


def _class_summary(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, list[float]] = {}
    for row in rows:
        out.setdefault(asset_class(str(row.get("asset") or "")), []).append(realised_r(row) or 0.0)
    return {cls: {"trades": len(v), "win_rate": round(sum(1 for r in v if r > 0) / len(v), 4),
                  "mean_r": round(sum(v) / len(v), 4)} for cls, v in out.items() if v}


def is_harmful(entry: dict[str, Any]) -> bool:
    return (entry.get("asset_class") != "all" and entry.get("factor") in GATE_FACTORS
            and float(entry.get("q", 1)) <= GATE_Q and int(entry.get("trades", 0)) >= GATE_MIN_TRADES
            and float(entry.get("mean_r_upper95", 0)) < 0 and float(entry.get("edge_r", 0)) < 0)


def harmful_lesson(snapshot: dict[str, Any] | None, setup: dict[str, Any]) -> dict[str, Any] | None:
    """The first evidence-backed losing context this setup is in, or None."""
    if not snapshot:
        return None
    cls = asset_class(str(setup.get("asset") or ""))
    present = factors(setup)
    for entry in snapshot.get("harmful") or []:
        if entry.get("asset_class") == cls and present.get(entry.get("factor")) == entry.get("value"):
            return entry
    return None


def review_trade(row: dict[str, Any], snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Why this trade worked or failed, what helped, what hurt, and what to change."""
    r = realised_r(row)
    present = factors(row)
    cls = asset_class(str(row.get("asset") or ""))
    table = (snapshot or {}).get("factors") or []
    index = {(t["asset_class"], t["factor"], t["value"]): t for t in table}
    helped, hurt = [], []
    for key, value in present.items():
        entry = index.get((cls, key, value)) or index.get(("all", key, value))
        if not entry or entry["q"] > LESSON_Q:
            continue
        (helped if entry["edge_r"] > 0 else hurt).append({**entry, "text": lesson_text(entry)})
    helped.sort(key=lambda t: -t["edge_r"])
    hurt.sort(key=lambda t: t["edge_r"])
    if r is None:
        headline = "Still open: watching it."
    elif r > 0:
        headline = f"Worked: TP1 reached, {r:+.2f}R."
    else:
        headline = "Did not work: stopped out, -1R."
    why = []
    if r is not None and r > 0:
        why = [f"{_LABELS.get(t['factor'], t['factor'])} {t['value'].replace('_', ' ')}" for t in helped[:3]]
        if not why:
            why = ["no single context stands out in the evidence; the setup's own edge carried it"]
    elif r is not None:
        why = [f"{_LABELS.get(t['factor'], t['factor'])} {t['value'].replace('_', ' ')}" for t in hurt[:3]]
        if not why:
            why = ["no measured risk context was present; this looks like a normal loss inside the setup's odds"]
    improve = [a for a in (_ADVICE.get((t["factor"], t["value"])) for t in hurt) if a]
    trend = next((t for t in (snapshot or {}).get("trends") or []
                  if t["asset_class"] == cls and t["strategy"] == str(row.get("strategy_name") or "")
                  and t["timeframe"] == str(row.get("timeframe") or "")), None)
    return {
        "asset": row.get("asset"), "timeframe": row.get("timeframe"), "strategy": row.get("strategy_name"),
        "direction": row.get("direction"), "asset_class": cls, "realised_r": r, "headline": headline,
        "why": why, "helped": helped[:5], "hurt": hurt[:5], "factors": present,
        "improve": improve[:3] or (["keep taking it as is: nothing in the evidence says change it"]
                                   if r is not None else []),
        "setup_trend": trend,
    }


def review_text(review: dict[str, Any]) -> str:
    lines = [review["headline"]]
    if review.get("why"):
        lines.append(("Why it worked: " if (review.get("realised_r") or 0) > 0 else "Why it failed: ")
                     + "; ".join(review["why"]) + ".")
    if review.get("improve"):
        lines.append("Next time: " + "; ".join(review["improve"]) + ".")
    trend = review.get("setup_trend")
    if trend and trend.get("direction") in {"improving", "worsening"}:
        lines.append(f"This setup type is {trend['direction']}: {trend['before_mean_r']:+.2f}R before, "
                     f"{trend['recent_mean_r']:+.2f}R in the last 30 days.")
    return "\n".join(lines)


def lessons_text(snapshot: dict[str, Any] | None, *, limit: int = 8) -> str:
    if not snapshot:
        return "No lessons yet: the first review runs after enough trades have resolved."
    lines = [f"Lessons from {snapshot.get('resolved_trades', 0)} resolved trades "
             f"(updated {str(snapshot.get('generated_at', ''))[:16].replace('T', ' ')} UTC):"]
    lessons = [t for t in snapshot.get("lessons") or [] if t.get("asset_class") != "all"] or \
        list(snapshot.get("lessons") or [])
    for t in lessons[:limit]:
        lines.append("• " + t["text"])
    if not lessons:
        lines.append("• No context has a statistically reliable effect yet.")
    if snapshot.get("harmful"):
        lines.append("Now avoided automatically (still tracked, so it can come back): "
                     + "; ".join(f"{t['asset_class']} {_LABELS.get(t['factor'], t['factor'])} "
                                 f"{t['value'].replace('_', ' ')}" for t in snapshot["harmful"][:5]) + ".")
    moving = [t for t in snapshot.get("trends") or [] if t.get("direction") in {"improving", "worsening"}]
    for t in moving[:3]:
        lines.append(f"• {t['asset_class']} {t['strategy']} {t['timeframe']} is {t['direction']} "
                     f"({t['before_mean_r']:+.2f}R → {t['recent_mean_r']:+.2f}R)")
    return "\n".join(lines)


# ---- runtime: build from the training dataset, store, read back --------------------------------------------

async def refresh(lookback_days: int = 365) -> dict[str, Any]:
    """Review every resolved trade in the lookback and store the snapshot."""
    import json

    from ml.train_model import load_training_data

    df = await load_training_data(lookback_days)
    rows = [] if df is None or len(df) == 0 else df.to_dict("records")
    rows = [r for r in rows if str(r.get("source_type") or "") not in excluded_sources()]
    snapshot = json.loads(json.dumps(build_snapshot(rows), default=str))
    from db.models import RuntimeState
    from db.session import get_session
    from utils.timeutils import now_utc_naive

    async with get_session(priority="analytics", label="trade_review_store", timeout_seconds=30) as session:
        row = await session.get(RuntimeState, SNAPSHOT_KEY)
        if row is None:
            session.add(RuntimeState(key=SNAPSHOT_KEY, value=snapshot, updated_at=now_utc_naive()))
        else:
            row.value = snapshot
            row.updated_at = now_utc_naive()
        await session.commit()
    _CACHE.update(snapshot=snapshot, at=_now())
    return snapshot


_CACHE: dict[str, Any] = {"snapshot": None, "at": 0.0}


def _now() -> float:
    import time

    return time.time()


async def load_snapshot(max_age_seconds: float = 600.0) -> dict[str, Any] | None:
    if _CACHE["snapshot"] is not None and _now() - float(_CACHE["at"]) < max_age_seconds:
        return _CACHE["snapshot"]
    try:
        from db.models import RuntimeState
        from db.session import get_session

        async with get_session(label="trade_review_read", timeout_seconds=5) as session:
            row = await session.get(RuntimeState, SNAPSHOT_KEY)
            value = dict(row.value or {}) if row is not None else None
    except Exception:
        return _CACHE["snapshot"]
    _CACHE.update(snapshot=value if isinstance(value, dict) else None, at=_now())
    return _CACHE["snapshot"]


async def trade_review_loop(stop) -> None:
    """Re-review every resolved trade on a schedule, so new outcomes become lessons on their own."""
    import asyncio
    import logging
    import os

    log = logging.getLogger(__name__)
    try:
        await asyncio.wait_for(stop.wait(), timeout=float(os.getenv("TRADE_REVIEW_STARTUP_DELAY_SECONDS", "900")))
        return
    except asyncio.TimeoutError:
        pass
    interval = max(1800.0, float(os.getenv("TRADE_REVIEW_INTERVAL_SECONDS", "21600") or 21600))
    while not stop.is_set():
        try:
            snap = await refresh(int(os.getenv("TRADE_REVIEW_LOOKBACK_DAYS", "365") or 365))
            log.info("[trade_review] resolved=%s lessons=%s harmful=%s overall=%s",
                     snap.get("resolved_trades"), len(snap.get("lessons") or []),
                     [f"{t['asset_class']}:{t['factor']}={t['value']}" for t in snap.get("harmful") or []],
                     snap.get("overall"))
        except Exception as exc:
            log.warning("[trade_review] refresh failed error=%s", type(exc).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue


def load_snapshot_sync(timeout: float = 3.0) -> dict[str, Any] | None:
    """Engine-thread accessor: the cached snapshot, refreshed from the database at most every 10 min."""
    if _CACHE["snapshot"] is not None and _now() - float(_CACHE["at"]) < 600.0:
        return _CACHE["snapshot"]
    try:
        from utils.async_runner import run_sync

        return run_sync(load_snapshot(), timeout=timeout)
    except Exception:
        _CACHE["at"] = _now()  # back off; a failed read must not cost every candidate a timeout
        return _CACHE["snapshot"]
