"""Rank retry candidates; reserve buckets and slots only after freshness checks."""
from __future__ import annotations

import math
from typing import Any, Iterable

from engine.delivery_freshness import evaluate_signal_age, evaluate_time_to_telegraph


def resend_payload(row: Any) -> dict[str, Any]:
    if hasattr(row, "__table__"):
        return {column.key: getattr(row, column.key, None) for column in row.__table__.columns}
    return dict(vars(row))


def has_fresh_resend(rows: Iterable[Any]) -> bool:
    """Let live opportunities take priority over optional stale-row writes."""
    for row in rows:
        payload = resend_payload(row)
        if evaluate_signal_age(payload).ok and evaluate_time_to_telegraph(payload).ok:
            return True
    return False


def rank_resend_candidates(rows: Iterable[Any], minimum_score: float) -> list[Any]:
    floor = float(minimum_score)
    if not math.isfinite(floor):
        return []
    ranked: list[tuple[float, Any]] = []
    for row in rows:
        try:
            raw_score = getattr(row, "score", None)
            if raw_score is None:
                continue
            score = float(raw_score)
            if not math.isfinite(score) or score < floor:
                continue
            if not all(str(getattr(row, key, "") or "").strip() for key in ("signal_id", "asset", "timeframe")):
                continue
            ranked.append((score, row))
        except (TypeError, ValueError, OverflowError):
            continue
    return [row for _, row in sorted(ranked, key=lambda item: item[0], reverse=True)]


def take_distinct_fresh_resends(rows: Iterable[Any], limit: int) -> list[Any]:
    """Consume already freshness-qualified rows in score order."""
    selected: list[Any] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        bucket = (str(row.asset).strip().upper(), str(row.timeframe).strip().lower())
        if bucket in seen:
            continue
        seen.add(bucket)
        selected.append(row)
        if len(selected) >= max(1, int(limit)):
            break
    return selected
