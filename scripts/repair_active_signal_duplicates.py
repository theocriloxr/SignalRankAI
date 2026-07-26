#!/usr/bin/env python3
"""Inspect or safely reconcile duplicate active SignalRankAI theses.

Dry-run is the default.  ``--apply`` preserves every row and all related
history; it only changes duplicate ``signals.status`` values to ``superseded``.
This script is an operational fallback.  Normal deployments should rely on the
Alembic migration.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, text


DUPLICATE_GROUPS_SQL = text(
    """
    SELECT asset, direction, timeframe, COUNT(*) AS active_count,
           ARRAY_AGG(signal_id ORDER BY created_at DESC NULLS LAST, signal_id DESC) AS signal_ids
    FROM signals
    WHERE status = 'active'
    GROUP BY asset, direction, timeframe
    HAVING COUNT(*) > 1
    ORDER BY active_count DESC, asset, direction, timeframe
    """
)

RECONCILE_SQL = text(
    """
    WITH active_candidates AS (
        SELECT
            s.signal_id,
            s.asset,
            s.direction,
            s.timeframe,
            s.created_at,
            CASE WHEN EXISTS (
                SELECT 1 FROM outcomes o
                WHERE o.signal_id = s.signal_id
                  AND LOWER(COALESCE(o.status, '')) IN ('active', 'tp1', 'tp2')
            ) THEN 1 ELSE 0 END AS has_open_outcome,
            CASE WHEN EXISTS (
                SELECT 1 FROM signal_deliveries d
                WHERE d.signal_id = s.signal_id
                  AND COALESCE(d.sent_ok, FALSE) IS TRUE
                  AND d.telegram_chat_id IS NOT NULL
                  AND d.telegram_message_id IS NOT NULL
            ) THEN 1 ELSE 0 END AS has_delivery_proof,
            COALESCE(dc.delivery_count, 0) AS delivery_count
        FROM signals s
        LEFT JOIN (
            SELECT signal_id, COUNT(*)::bigint AS delivery_count
            FROM signal_deliveries GROUP BY signal_id
        ) dc ON dc.signal_id = s.signal_id
        WHERE s.status = 'active'
    ), ranked AS (
        SELECT *,
            ROW_NUMBER() OVER (
                PARTITION BY asset, direction, timeframe
                ORDER BY has_open_outcome DESC, has_delivery_proof DESC,
                         delivery_count DESC, created_at DESC NULLS LAST,
                         signal_id DESC
            ) AS row_num,
            FIRST_VALUE(signal_id) OVER (
                PARTITION BY asset, direction, timeframe
                ORDER BY has_open_outcome DESC, has_delivery_proof DESC,
                         delivery_count DESC, created_at DESC NULLS LAST,
                         signal_id DESC
            ) AS canonical_signal_id
        FROM active_candidates
    ), duplicates AS (
        SELECT * FROM ranked WHERE row_num > 1
    ), audit AS (
        INSERT INTO admin_events(event_type, actor_telegram_user_id, details, created_at)
        SELECT 'ops_active_signal_dedupe', NULL,
               json_build_object(
                   'superseded_signal_id', signal_id,
                   'canonical_signal_id', canonical_signal_id,
                   'asset', asset,
                   'direction', direction,
                   'timeframe', timeframe,
                   'had_open_outcome', (has_open_outcome = 1),
                   'had_delivery_proof', (has_delivery_proof = 1),
                   'delivery_count', delivery_count,
                   'rows_deleted', 0
               ), NOW()
        FROM duplicates
        RETURNING 1
    )
    UPDATE signals s
    SET status = 'superseded'
    FROM duplicates d
    WHERE s.signal_id = d.signal_id
    RETURNING s.signal_id, d.canonical_signal_id, s.asset, s.direction, s.timeframe
    """
)


def _sync_url(raw: str) -> str:
    return (
        raw.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
        .replace("postgres://", "postgresql+psycopg2://", 1)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply the non-destructive status reconciliation")
    parser.add_argument("--output", default="", help="Optional JSON report path")
    args = parser.parse_args()

    raw_url = str(os.getenv("DATABASE_URL") or "").strip()
    if not raw_url:
        raise SystemExit("DATABASE_URL is required")

    engine = create_engine(_sync_url(raw_url), pool_pre_ping=True)
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry_run",
        "groups_before": [],
        "changed": [],
        "groups_after": [],
        "rows_deleted": 0,
    }

    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('signalrank:active_signal_guard'))"))
        report["groups_before"] = [dict(row._mapping) for row in conn.execute(DUPLICATE_GROUPS_SQL)]
        if args.apply and report["groups_before"]:
            report["changed"] = [dict(row._mapping) for row in conn.execute(RECONCILE_SQL)]
            conn.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS ix_signals_active_thesis
                    ON signals (asset, direction, timeframe)
                    WHERE status = 'active'
                    """
                )
            )
        report["groups_after"] = [dict(row._mapping) for row in conn.execute(DUPLICATE_GROUPS_SQL)]

    rendered = json.dumps(report, indent=2, default=str, sort_keys=True)
    print(rendered)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")

    if args.apply and report["groups_after"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
