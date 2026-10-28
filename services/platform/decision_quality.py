"""Decision-quality report shared by the web Quality view and Telegram /quality.

Both channels read the same ``decision_log`` window through this module so a
signal drought looks identical wherever the person asks (CX-SIG-21, CX-CHAN-01).
The caller owns the session; the report only reads.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text

BREAKDOWN_DIMENSIONS = ("asset", "timeframe", "strategy", "layer")
UNATTRIBUTED = {"asset": "(no asset)", "timeframe": "(no timeframe)",
                "strategy": "(unattributed)", "layer": "(no layer)"}

_REASON_SQL = """
    SELECT decision, COALESCE(reason, '') AS reason, COUNT(*) AS rows
    FROM decision_log
    WHERE created_at >= :cutoff
    GROUP BY decision, reason
    ORDER BY COUNT(*) DESC
"""

# One scan of the same window, split four ways. A missing strategy is reported
# as unattributed, never inferred.
_DIMENSION_SQL = """
    SELECT CASE WHEN GROUPING(asset) = 0 THEN 'asset'
                WHEN GROUPING(timeframe) = 0 THEN 'timeframe'
                WHEN GROUPING(COALESCE(meta->>'strategy', meta->>'strategy_name')) = 0 THEN 'strategy'
                ELSE 'layer' END AS dimension,
           COALESCE(asset, timeframe, COALESCE(meta->>'strategy', meta->>'strategy_name'), meta->>'layer') AS value,
           LOWER(COALESCE(decision, '')) AS decision,
           COUNT(*) AS rows
    FROM decision_log
    WHERE created_at >= :cutoff
    GROUP BY GROUPING SETS (
        (asset, decision),
        (timeframe, decision),
        (COALESCE(meta->>'strategy', meta->>'strategy_name'), decision),
        (meta->>'layer', decision)
    )
"""


def _reject_bucket(reason: str) -> str:
    if "slippage" in reason:
        return "slippage"
    if "stale" in reason:
        return "stale"
    if "news" in reason:
        return "news"
    if "ml" in reason:
        return "ml"
    if "score" in reason:
        return "score"
    return "other"


def quality_breakdowns(rows: Any, limit: int = 12) -> dict[str, list[dict[str, Any]]]:
    """Issued vs rejected decisions per asset, timeframe, strategy and pipeline layer."""
    tallies: dict[str, dict[str, dict[str, int]]] = {name: {} for name in BREAKDOWN_DIMENSIONS}
    for row in rows or []:
        dimension = str(row.get("dimension") or "")
        if dimension not in tallies:
            continue
        value = str(row.get("value") or "").strip() or UNATTRIBUTED[dimension]
        decision = str(row.get("decision") or "")
        count = int(row.get("rows") or 0)
        entry = tallies[dimension].setdefault(value, {"issued": 0, "rejected_or_skipped": 0, "other": 0})
        if decision == "issued":
            entry["issued"] += count
        elif decision in {"rejected", "skipped"}:
            entry["rejected_or_skipped"] += count
        else:
            entry["other"] += count
    result: dict[str, list[dict[str, Any]]] = {}
    for dimension, values in tallies.items():
        ordered = sorted(values.items(), key=lambda item: (-item[1]["rejected_or_skipped"], -item[1]["issued"], item[0]))
        result[dimension] = [
            {
                "value": value,
                **counts,
                "acceptance_rate": (
                    counts["issued"] / (counts["issued"] + counts["rejected_or_skipped"])
                    if counts["issued"] + counts["rejected_or_skipped"] else None
                ),
            }
            for value, counts in ordered[: max(1, int(limit))]
        ]
    return result


def summarize_decisions(reason_rows: Any, dimension_rows: Any, *, hours: int) -> dict[str, Any]:
    """Shape both scans into the report both channels present."""
    issued = 0
    rejected = 0
    buckets = {"score": 0, "ml": 0, "news": 0, "stale": 0, "slippage": 0, "other": 0}
    reason_counts: dict[str, int] = {}
    for row in reason_rows or []:
        decision = str(row.get("decision") or "").lower()
        reason = str(row.get("reason") or "").lower()
        count = int(row.get("rows") or 0)
        if decision == "issued":
            issued += count
        if decision in {"rejected", "skipped"}:
            rejected += count
            reason_counts[reason or "(empty)"] = reason_counts.get(reason or "(empty)", 0) + count
            buckets[_reject_bucket(reason)] += count
    total = issued + rejected
    top_reasons = sorted(reason_counts.items(), key=lambda item: item[1], reverse=True)[:10]
    return {
        "window_hours": int(hours),
        "issued": issued,
        "rejected_or_skipped": rejected,
        "acceptance_rate": (issued / total if total else None),
        "reject_buckets": buckets,
        "top_reasons": [{"reason": reason, "rows": count} for reason, count in top_reasons],
        "breakdowns": quality_breakdowns(dimension_rows),
    }


async def decision_quality_report(session: Any, *, hours: int = 24) -> dict[str, Any]:
    """Read the decision window and return the shared quality report."""
    cutoff = datetime.utcnow() - timedelta(hours=int(hours))
    reason_rows = (await session.execute(text(_REASON_SQL), {"cutoff": cutoff})).mappings().all()
    dimension_rows = (await session.execute(text(_DIMENSION_SQL), {"cutoff": cutoff})).mappings().all()
    return summarize_decisions(reason_rows, dimension_rows, hours=int(hours))


__all__ = [
    "BREAKDOWN_DIMENSIONS", "UNATTRIBUTED", "decision_quality_report",
    "quality_breakdowns", "summarize_decisions",
]
