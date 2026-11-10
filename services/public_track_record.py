"""Public, live track record (9 Nov 2026; learned from competitor research).

Danelfin publishes backtested headline figures; Token Metrics states each
alert's invalidation; honest Telegram channels publish their misses. SignalRank
publishes its live record: every delivered signal that has closed, misses
included, per asset class over 7 and 30 days, and the latest closed calls.

Only signals that were actually delivered (a confirmed delivery row) and whose
outcome is eligible for performance accounting are counted. Results are in R
(multiples of the planned risk), gross of fees and slippage. Exact entry/stop
levels are not published: the record shows instrument, side, timeframe,
strategy, result and time.
"""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import text

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_TTL_SECONDS = 300.0

_WIN = "('tp','tp1','tp2','tp3','partial_tp','win','partial_win')"
_LOSS = "('sl','loss','stop_loss')"

_CLASS_SQL = f"""
    SELECT COALESCE(NULLIF(s.asset_class, ''), 'other') AS asset_class,
           COUNT(*) AS closed,
           COUNT(*) FILTER (WHERE lower(COALESCE(o.canonical_outcome, o.status, '')) IN {_WIN}) AS reached_tp1,
           COUNT(*) FILTER (WHERE lower(COALESCE(o.canonical_outcome, o.status, '')) IN {_LOSS}) AS stopped,
           AVG(o.r_multiple) AS avg_r,
           SUM(o.r_multiple) AS total_r
    FROM outcomes o
    JOIN signals s ON s.signal_id = o.signal_id
    WHERE o.closed_at >= (NOW() AT TIME ZONE 'utc') - make_interval(days => :days)
      AND o.r_multiple IS NOT NULL
      AND COALESCE(o.performance_inclusion_status, 'eligible') = 'eligible'
      AND EXISTS (SELECT 1 FROM signal_deliveries d WHERE d.signal_id = s.signal_id
                  AND (d.delivery_confirmed_at IS NOT NULL OR d.delivered_at IS NOT NULL))
    GROUP BY 1 ORDER BY 2 DESC
"""

_RECENT_SQL = f"""
    SELECT s.asset, COALESCE(NULLIF(s.asset_class, ''), 'other') AS asset_class, s.direction, s.timeframe,
           s.strategy_name, COALESCE(o.canonical_outcome, o.status) AS outcome, o.r_multiple, o.closed_at,
           s.created_at
    FROM outcomes o
    JOIN signals s ON s.signal_id = o.signal_id
    WHERE o.closed_at IS NOT NULL AND o.r_multiple IS NOT NULL
      AND COALESCE(o.performance_inclusion_status, 'eligible') = 'eligible'
      AND EXISTS (SELECT 1 FROM signal_deliveries d WHERE d.signal_id = s.signal_id
                  AND (d.delivery_confirmed_at IS NOT NULL OR d.delivered_at IS NOT NULL))
    ORDER BY o.closed_at DESC
    LIMIT :limit
"""


def _num(value: Any, digits: int = 3) -> float | None:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)


async def build_track_record(session: Any, *, recent: int = 25) -> dict[str, Any]:
    windows: dict[str, list[dict[str, Any]]] = {}
    for days in (7, 30):
        rows = (await session.execute(text(_CLASS_SQL), {"days": days})).mappings().all()
        windows[f"{days}d"] = [
            {
                "asset_class": str(r["asset_class"]),
                "closed": int(r["closed"] or 0),
                "reached_tp1": int(r["reached_tp1"] or 0),
                "stopped": int(r["stopped"] or 0),
                "tp1_rate": _num((r["reached_tp1"] or 0) / r["closed"], 4) if r["closed"] else None,
                "avg_r": _num(r["avg_r"]),
                "total_r": _num(r["total_r"]),
            }
            for r in rows
        ]
    recent_rows = (await session.execute(text(_RECENT_SQL), {"limit": int(recent)})).mappings().all()
    return {
        "generated_at": time.time(),
        "basis": "live_delivered_signals_only",
        "units": "R (multiples of the planned risk), gross of fees and slippage",
        "disclaimer": "Past results do not guarantee future results. Signals are research, not financial advice.",
        "windows": windows,
        "recent": [
            {
                "asset": r["asset"], "asset_class": r["asset_class"], "direction": r["direction"],
                "timeframe": r["timeframe"], "strategy": r["strategy_name"], "outcome": r["outcome"],
                "r": _num(r["r_multiple"]), "closed_at": _iso(r["closed_at"]), "sent_at": _iso(r["created_at"]),
            }
            for r in recent_rows
        ],
    }


async def cached_track_record(session_factory) -> dict[str, Any]:
    hit = _CACHE.get("record")
    if hit and time.monotonic() - hit[0] < _TTL_SECONDS:
        return hit[1]
    async with session_factory() as session:
        record = await build_track_record(session)
        await session.rollback()
    _CACHE["record"] = (time.monotonic(), record)
    return record


def weekly_scorecard_text(record: dict[str, Any]) -> str:
    """Plain weekly scorecard for Telegram/email: every class, misses included."""
    rows = record.get("windows", {}).get("7d") or []
    if not rows:
        return "📊 Weekly scorecard: no signal closed in the last 7 days."
    lines = ["📊 SignalRank weekly scorecard (live, delivered signals; R = multiples of planned risk)"]
    total_closed = sum(r["closed"] for r in rows)
    total_r = sum(r["total_r"] or 0.0 for r in rows)
    for r in rows:
        rate = f"{r['tp1_rate'] * 100:.0f}%" if r["tp1_rate"] is not None else "n/a"
        lines.append(f"• {r['asset_class']}: {r['closed']} closed, {r['reached_tp1']} reached TP1 ({rate}), "
                     f"{r['stopped']} stopped, {r['total_r']:+.2f}R")
    lines.append(f"Total: {total_closed} closed, {total_r:+.2f}R. Every call, wins and misses, is on the public record.")
    lines.append("Past results do not guarantee future results.")
    return "\n".join(lines)
