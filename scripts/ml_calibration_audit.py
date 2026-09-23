#!/usr/bin/env python
"""Read-only ML calibration evidence audit.

This replaces the old Railway shell/base64 psql payload. All statements are
static, quoted SQL executed through SQLAlchemy, and the transaction is forced
READ ONLY so the audit cannot mutate production.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from sqlalchemy import text

from db.session import get_session, is_db_configured


ML_PAST_SQL = text(
    """
    SELECT
        COUNT(*) AS total,
        COUNT(*) FILTER (WHERE delivery_proof_backed IS TRUE) AS proof_backed,
        COUNT(*) FILTER (
            WHERE lower(COALESCE(outcome_status, '')) IN
                ('win','tp','tp1','tp2','tp3','partial_tp')
        ) AS positive,
        COUNT(*) FILTER (
            WHERE lower(COALESCE(outcome_status, '')) IN
                ('loss','sl','stop_loss','time_stop')
        ) AS negative
    FROM ml_past_training_data
    WHERE COALESCE(signal_created_at, archived_at)
        >= NOW() - make_interval(days => :days)
    """
)

REJECTED_SQL = text(
    """
    SELECT
        COUNT(*) AS total,
        COUNT(*) FILTER (
            WHERE lower(COALESCE(actual_outcome, '')) IN
                ('win','loss','tp','tp1','tp2','tp3','sl','stop_loss')
        ) AS resolved,
        COUNT(DISTINCT signal_id) FILTER (
            WHERE signal_id IS NOT NULL
              AND lower(COALESCE(actual_outcome, '')) IN
                ('win','loss','tp','tp1','tp2','tp3','sl','stop_loss')
        ) AS unique_signals
    FROM ml_rejected_signals
    WHERE created_at >= NOW() - make_interval(days => :days)
    """
)

PAPER_SQL = text(
    """
    SELECT
        COUNT(*) AS total,
        COUNT(*) FILTER (WHERE closed_at IS NOT NULL) AS closed,
        COUNT(DISTINCT signal_id) FILTER (WHERE closed_at IS NOT NULL) AS unique_signals
    FROM paper_positions
    WHERE opened_at >= NOW() - make_interval(days => :days)
    """
)

UNIQUE_IDS_SQL = text(
    """
    WITH ids AS (
        SELECT signal_id
        FROM ml_past_training_data
        WHERE signal_id IS NOT NULL
          AND COALESCE(signal_created_at, archived_at)
              >= NOW() - make_interval(days => :days)

        UNION

        SELECT signal_id
        FROM ml_rejected_signals
        WHERE created_at >= NOW() - make_interval(days => :days)
          AND signal_id IS NOT NULL
          AND lower(COALESCE(actual_outcome, '')) IN
              ('win','loss','tp','tp1','tp2','tp3','sl','stop_loss')

        UNION

        SELECT signal_id
        FROM paper_positions
        WHERE opened_at >= NOW() - make_interval(days => :days)
          AND signal_id IS NOT NULL
          AND closed_at IS NOT NULL
    )
    SELECT COUNT(*) AS total FROM ids
    """
)


def _mapping(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    mapping = getattr(row, "_mapping", None)
    data = dict(mapping if mapping is not None else row)
    return {str(k): (int(v) if isinstance(v, int) else v) for k, v in data.items()}


async def run_audit(days: int = 180) -> dict[str, Any]:
    if not is_db_configured():
        raise RuntimeError("database_not_configured")
    days = max(1, min(3650, int(days)))

    async with get_session(
        priority="analytics",
        label="ml_calibration_audit",
        timeout_seconds=60.0,
        drop_if_busy=False,
    ) as session:
        # Must be the first transactional command. PostgreSQL then rejects any
        # accidental write attempted by this audit.
        await session.execute(text("SET TRANSACTION READ ONLY"))

        ml_past = _mapping((await session.execute(ML_PAST_SQL, {"days": days})).first())
        rejected = _mapping((await session.execute(REJECTED_SQL, {"days": days})).first())
        paper = _mapping((await session.execute(PAPER_SQL, {"days": days})).first())
        unique = _mapping((await session.execute(UNIQUE_IDS_SQL, {"days": days})).first())
        await session.rollback()

    return {
        "ok": True,
        "read_only": True,
        "lookback_days": days,
        "ml_past": ml_past,
        "rejected": rejected,
        "paper": paper,
        "unique_signal_ids": int(unique.get("total") or 0),
    }


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Read-only SignalRank ML calibration audit")
    parser.add_argument("--days", type=int, default=180)
    args = parser.parse_args()
    try:
        result = await run_audit(args.days)
    except Exception as exc:
        print(json.dumps({
            "ok": False,
            "read_only": True,
            "error": type(exc).__name__,
            "detail": str(exc)[:400],
        }, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
