"""Evidence-based setup filter (owner decision, 2 Nov 2026).

A setup (strategy x timeframe x direction) may produce signals only while its
proven rate of reaching TP1 beats the break-even rate of the plan it publishes.
Nothing here is a hand-picked threshold:

* proven rate: the Wilson lower confidence bound of TP1-or-better over resolved
  trades, so a small sample cannot look better than it has shown;
* break-even rate: from the signal's own levels and the published exit plan
  (close ``SIGNAL_TP1_CLOSE_FRACTION`` at TP1, remainder protected at entry,
  a loss costs 1R): p * f1 * rr_tp1 = (1 - p)  ->  p = 1 / (1 + f1 * rr_tp1);
* evidence: every resolved trade the platform tracked in the window — shadow
  outcomes of generated candidates (ml_rejected_signals) and outcomes of
  delivered signals.

The aggregate takes seconds over the shadow table, so the worker refreshes a
snapshot in runtime_state and the engine reads only the snapshot.
"""
from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from statistics import NormalDist
from typing import Any, Mapping

SNAPSHOT_KEY = "segment_evidence:v1"
WIN_SHADOW = ("tp1", "tp2", "tp3")
WIN_OUTCOME = ("tp", "tp1", "tp2", "tp3", "partial_tp", "partial_win_be")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


def confidence_z() -> float:
    """One-sided z for SEGMENT_EVIDENCE_CONFIDENCE (default 0.95)."""
    confidence = min(0.999, max(0.5, _env_float("SEGMENT_EVIDENCE_CONFIDENCE", 0.95)))
    return NormalDist().inv_cdf(confidence)


def wilson_lower_bound(wins: int, n: int, z: float) -> float:
    if n <= 0:
        return 0.0
    p = wins / n
    denominator = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - margin) / denominator)


def breakeven_tp1_rate(rr_tp1: float) -> float | None:
    """TP1-or-better rate at which the published plan neither makes nor loses R."""
    from core.partial_exit_accounting import planned_exit_fractions

    tp1_fraction = planned_exit_fractions()[0]
    payoff = tp1_fraction * float(rr_tp1)
    if not math.isfinite(payoff) or payoff <= 0:
        return None
    return 1.0 / (1.0 + payoff)


def canonical_direction(value: Any) -> str:
    probe = str(value or "").strip().lower()
    if probe in {"long", "buy", "bull", "bullish"}:
        return "long"
    if probe in {"short", "sell", "bear", "bearish"}:
        return "short"
    return ""


def segment_key(strategy: Any, timeframe: Any, direction: Any) -> str:
    return "|".join((str(strategy or "").strip().lower(), str(timeframe or "").strip().lower(),
                     canonical_direction(direction)))


def tp1_reward_risk(signal: Mapping[str, Any]) -> float | None:
    try:
        entry = float(signal.get("entry"))
        stop = float(signal.get("stop_loss") if signal.get("stop_loss") is not None else signal.get("stop"))
    except (TypeError, ValueError):
        return None
    targets: Any = signal.get("take_profit") or signal.get("take_profits") or signal.get("targets")
    if isinstance(targets, str):
        try:
            targets = json.loads(targets)
        except ValueError:
            targets = [targets]
    if not isinstance(targets, (list, tuple)):
        targets = [targets]
    for item in targets:
        candidate = item.get("price") if isinstance(item, dict) else item
        try:
            tp1 = float(candidate)
        except (TypeError, ValueError):
            continue
        if tp1 > 0 and entry > 0 and stop > 0 and entry != stop:
            return abs(tp1 - entry) / abs(entry - stop)
    return None


@dataclass(frozen=True)
class SegmentDecision:
    allowed: bool
    reason: str
    key: str
    trades: int = 0
    wins: int = 0
    lower_bound: float | None = None
    breakeven: float | None = None


def evaluate(signal: Mapping[str, Any], segments: Mapping[str, Any]) -> SegmentDecision:
    key = segment_key(signal.get("strategy_name") or signal.get("strategy"), signal.get("timeframe"),
                      signal.get("direction"))
    rr = tp1_reward_risk(signal)
    breakeven = breakeven_tp1_rate(rr) if rr is not None else None
    if breakeven is None:
        return SegmentDecision(False, f"segment_evidence {key}: no valid TP1 reward/risk", key)
    row = segments.get(key) or {}
    trades, wins = int(row.get("n") or 0), int(row.get("wins") or 0)
    lower = wilson_lower_bound(wins, trades, confidence_z())
    detail = f"{wins}/{trades} reached TP1, lower bound {lower:.1%} vs break-even {breakeven:.1%}"
    if lower > breakeven:
        return SegmentDecision(True, f"segment_evidence {key}: {detail}", key, trades, wins, lower, breakeven)
    return SegmentDecision(False, f"segment_evidence {key}: {detail}", key, trades, wins, lower, breakeven)


# The engine re-logs the same rejected setup on every scan (one bar could yield
# thousands of identical rows), so shadow evidence counts one setup per asset,
# timeframe, strategy, direction and bar: the first logged row of that bar.
# Read one hour at a time through the created_at index: the whole window in one
# statement reads gigabytes and outlasts the driver's command timeout (a busy
# day alone took 21 s on production on 2 Nov). Windows
# run oldest first and bars already counted are skipped, so a bar that spans
# two windows still counts once.
SHADOW_WINDOW_SQL = """
SELECT DISTINCT ON (asset, tf, strategy, direction, bar) asset, tf, strategy, direction, bar, outcome
FROM (
    SELECT asset, lower(timeframe) AS tf, lower(features->>'strategy_name') AS strategy,
           lower(direction) AS direction, lower(actual_outcome) AS outcome, created_at,
           floor(extract(epoch FROM created_at) / CASE lower(timeframe)
               WHEN '1m' THEN 60 WHEN '3m' THEN 180 WHEN '5m' THEN 300 WHEN '15m' THEN 900
               WHEN '30m' THEN 1800 WHEN '1h' THEN 3600 WHEN '2h' THEN 7200 WHEN '4h' THEN 14400
               WHEN '6h' THEN 21600 WHEN '8h' THEN 28800 WHEN '12h' THEN 43200 WHEN '1d' THEN 86400
               WHEN '24h' THEN 86400 WHEN '1w' THEN 604800 ELSE 3600 END) AS bar
    FROM ml_rejected_signals
    WHERE created_at >= :start AND created_at < :end AND lower(actual_outcome) IN ('sl','tp1','tp2','tp3')
) AS rows
ORDER BY asset, tf, strategy, direction, bar, created_at
"""
OUTCOME_SQL = """
SELECT lower(s.strategy_name), lower(s.timeframe), lower(s.direction), COUNT(*),
       COUNT(*) FILTER (WHERE lower(o.status) IN ('tp','tp1','tp2','tp3','partial_tp','partial_win_be'))
FROM outcomes o JOIN signals s ON s.signal_id = o.signal_id
WHERE o.closed_at >= :since
  AND lower(o.status) IN ('sl','tp','tp1','tp2','tp3','partial_tp','partial_win_be')
GROUP BY 1, 2, 3
"""


def _add(segments: dict[str, dict[str, int]], strategy, timeframe, direction, n: int, wins: int) -> None:
    key = segment_key(strategy, timeframe, direction)
    if not key.endswith("|") and n > 0:
        row = segments.setdefault(key, {"n": 0, "wins": 0})
        row["n"] += n
        row["wins"] += wins


async def compute_snapshot(session, *, now: float | None = None) -> dict[str, Any]:
    from datetime import timedelta

    from sqlalchemy import text

    from utils.timeutils import now_utc_naive

    lookback = max(1.0, _env_float("SEGMENT_EVIDENCE_LOOKBACK_DAYS", 60.0))
    end = now_utc_naive()
    since = end - timedelta(days=lookback)
    segments: dict[str, dict[str, int]] = {}
    seen: set[tuple] = set()
    start = since
    while start < end:
        stop = min(end, start + timedelta(hours=1))
        rows = (await session.execute(text(SHADOW_WINDOW_SQL), {"start": start, "end": stop})).all()
        for asset, timeframe, strategy, direction, bar, outcome in rows:
            bar_key = (asset, timeframe, strategy, direction, bar)
            if bar_key not in seen:
                seen.add(bar_key)
                _add(segments, strategy, timeframe, direction, 1, int(outcome in WIN_SHADOW))
        start = stop
    for strategy, timeframe, direction, n, wins in (await session.execute(text(OUTCOME_SQL), {"since": since})).all():
        _add(segments, strategy, timeframe, direction, int(n or 0), int(wins or 0))
    return {"computed_at": float(now if now is not None else time.time()), "lookback_days": lookback,
            "segments": segments}


async def store_snapshot(session, snapshot: Mapping[str, Any]) -> None:
    from sqlalchemy import text

    await session.execute(
        text("INSERT INTO runtime_state(key, value, expires_at, updated_at) VALUES (:key, CAST(:value AS JSONB), NULL, NOW()) "
             "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()"),
        {"key": SNAPSHOT_KEY, "value": json.dumps(dict(snapshot))},
    )


async def load_snapshot(session) -> dict[str, Any] | None:
    from sqlalchemy import text

    value = (await session.execute(text("SELECT value FROM runtime_state WHERE key = :key"),
                                   {"key": SNAPSHOT_KEY})).scalar_one_or_none()
    if isinstance(value, str):
        value = json.loads(value)
    return dict(value) if isinstance(value, dict) else None


def snapshot_is_current(snapshot: Mapping[str, Any] | None, *, now: float | None = None) -> bool:
    """Current while younger than two refresh intervals."""
    if not snapshot:
        return False
    interval = max(60.0, _env_float("SEGMENT_EVIDENCE_REFRESH_SECONDS", 900.0))
    age = float(now if now is not None else time.time()) - float(snapshot.get("computed_at") or 0)
    return 0 <= age <= 2 * interval


def record_for(signal: Mapping[str, Any], segments: Mapping[str, Any]) -> dict[str, Any] | None:
    """The setup's real 60-day record for display; None when there is none to show."""
    decision = evaluate(signal, segments)
    if decision.trades <= 0:
        return None
    return {"key": decision.key, "trades": decision.trades, "wins": decision.wins,
            "lower_bound": decision.lower_bound, "breakeven": decision.breakeven}


async def attach_records(signals: list[dict[str, Any]]) -> None:
    """Attach the current setup record to signals that do not carry one.

    Signals delivered from the database lose the record the engine attached.
    The card shows the record as it stands now, or nothing: never an invented one.
    """
    pending = [s for s in signals if isinstance(s, dict) and not s.get("segment_evidence")]
    if not pending:
        return
    from db.priority import DBPriority
    from db.session import get_session

    try:
        async with get_session(priority=DBPriority.BACKGROUND, label="segment_evidence_display",
                               timeout_seconds=3.0) as session:
            snapshot = await load_snapshot(session)
            await session.rollback()
    except Exception:
        return
    if not snapshot_is_current(snapshot):
        return
    segments = dict((snapshot or {}).get("segments") or {})
    for signal in pending:
        record = record_for(signal, segments)
        if record:
            signal["segment_evidence"] = record


async def refresh_once() -> int:
    """Worker task: recompute and store the snapshot. Returns the number of segments.

    Production 10-11 Nov 2026: the whole 60-day scan (1,440 hourly reads) ran in one
    session with a 30 s budget. On a busy database it timed out every time, the
    snapshot went 19 hours stale and the fail-closed setup filter rejected every
    candidate. Each hour window now gets its own short session and a few retries;
    the snapshot is stored only when every window was read (no partial evidence).
    """
    import asyncio
    from datetime import timedelta

    from sqlalchemy import text

    from db.priority import DBPriority
    from db.session import get_session
    from utils.timeutils import now_utc_naive

    lookback = max(1.0, _env_float("SEGMENT_EVIDENCE_LOOKBACK_DAYS", 60.0))
    end = now_utc_naive()
    since = end - timedelta(days=lookback)
    segments: dict[str, dict[str, int]] = {}
    seen: set[tuple] = set()

    async def _read(sql: str, params: dict, label: str):
        for attempt in range(1, 4):
            try:
                async with get_session(priority=DBPriority.BACKGROUND, label=label, timeout_seconds=60.0) as session:
                    rows = (await session.execute(text(sql), params)).all()
                    await session.rollback()
                    return rows
            except Exception:
                if attempt == 3:
                    raise
                await asyncio.sleep(2.0 * attempt)
        return []

    start = since
    while start < end:  # one hour per statement: index-friendly, proven on production
        stop = min(end, start + timedelta(hours=1))
        for asset, timeframe, strategy, direction, bar, outcome in await _read(
                SHADOW_WINDOW_SQL, {"start": start, "end": stop}, "segment_evidence_refresh.window"):
            bar_key = (asset, timeframe, strategy, direction, bar)
            if bar_key not in seen:
                seen.add(bar_key)
                _add(segments, strategy, timeframe, direction, 1, int(outcome in WIN_SHADOW))
        start = stop
    for strategy, timeframe, direction, n, wins in await _read(OUTCOME_SQL, {"since": since},
                                                               "segment_evidence_refresh.outcomes"):
        _add(segments, strategy, timeframe, direction, int(n or 0), int(wins or 0))
    snapshot = {"computed_at": time.time(), "lookback_days": lookback, "segments": segments}
    async with get_session(priority=DBPriority.BACKGROUND, label="segment_evidence_refresh.store",
                           timeout_seconds=30.0) as session:
        await store_snapshot(session, snapshot)
        await session.commit()
    return len(snapshot["segments"])
