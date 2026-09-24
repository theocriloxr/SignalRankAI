#!/usr/bin/env python3
"""Read-only aggregate runtime audit for staging/production certification.

This script never mutates data and never emits secrets or per-user identifiers.
It is intended for one-off Railway certification services.
"""
from __future__ import annotations

import json
import os
from typing import Any

import psycopg2

from db.database_urls import normalize_psycopg2_dsn


def _query(cur, sql: str) -> Any:
    try:
        cur.execute("SET statement_timeout TO 15000")
        cur.execute(sql)
        if not cur.description:
            return []
        columns = [item[0] for item in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
    except Exception as exc:
        try:
            cur.connection.rollback()
        except Exception:
            pass
        return {"error": f"{type(exc).__name__}:{str(exc)[:180]}"}


def main() -> int:
    dsn = normalize_psycopg2_dsn(os.environ["DATABASE_URL"])
    conn = psycopg2.connect(dsn, connect_timeout=10)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        try:
            result = {
                "artifacts": _query(
                    cur,
                    """
                    SELECT model_name, artifact_hash_sha256, is_active, trained_at, created_at,
                           metrics, source_counts,
                           payload->>'trained_at' AS payload_trained_at,
                           payload->'metrics' AS payload_metrics
                    FROM ml_model_artifacts
                    WHERE model_name IN ('primary','candidate')
                    ORDER BY created_at DESC
                    LIMIT 16
                    """,
                ),
                "signals_7d": _query(
                    cur,
                    """
                    SELECT COALESCE(asset_class,'unknown') AS asset_class,
                           COUNT(*) AS signals,
                           COUNT(*) FILTER (
                               WHERE lower(COALESCE(status,'')) IN ('open','pending','active')
                           ) AS openish,
                           COUNT(*) FILTER (
                               WHERE created_at < NOW()-INTERVAL '24 hours'
                                 AND lower(COALESCE(status,'')) IN ('open','pending','active')
                           ) AS stale_openish
                    FROM signals
                    WHERE created_at >= NOW()-INTERVAL '7 days'
                    GROUP BY 1 ORDER BY 1
                    """,
                ),
                "deliveries_7d": _query(
                    cur,
                    """
                    SELECT COALESCE(s.asset_class,'unknown') AS asset_class,
                           COUNT(*) AS deliveries,
                           COUNT(*) FILTER (WHERE d.sent_ok IS TRUE) AS sent_ok,
                           COUNT(DISTINCT d.signal_id) AS distinct_signals
                    FROM signal_deliveries d
                    JOIN signals s ON s.signal_id=d.signal_id
                    WHERE COALESCE(d.delivered_at,d.created_at) >= NOW()-INTERVAL '7 days'
                    GROUP BY 1 ORDER BY 1
                    """,
                ),
                "outcomes_7d": _query(
                    cur,
                    """
                    SELECT COALESCE(s.asset_class,'unknown') AS asset_class,
                           lower(COALESCE(o.canonical_outcome,o.status,'unknown')) AS outcome,
                           COUNT(*) AS rows,
                           AVG(o.r_multiple) AS avg_r
                    FROM outcomes o
                    JOIN signals s ON s.signal_id=o.signal_id
                    WHERE COALESCE(o.closed_at,s.created_at) >= NOW()-INTERVAL '7 days'
                    GROUP BY 1,2 ORDER BY 1,2
                    """,
                ),
                "lifecycle_gaps_7d": _query(
                    cur,
                    """
                    SELECT COALESCE(s.asset_class,'unknown') AS asset_class,
                           COUNT(*) FILTER (WHERE d.signal_id IS NULL) AS no_successful_delivery,
                           COUNT(*) FILTER (
                               WHERE d.signal_id IS NOT NULL
                                 AND o.signal_id IS NULL
                                 AND s.created_at < NOW()-INTERVAL '24 hours'
                           ) AS delivered_no_outcome_24h
                    FROM signals s
                    LEFT JOIN (
                        SELECT DISTINCT signal_id
                        FROM signal_deliveries
                        WHERE sent_ok IS TRUE
                    ) d ON d.signal_id=s.signal_id
                    LEFT JOIN outcomes o ON o.signal_id=s.signal_id
                    WHERE s.created_at >= NOW()-INTERVAL '7 days'
                    GROUP BY 1 ORDER BY 1
                    """,
                ),
                "profile_state": _query(
                    cur,
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE key LIKE 'trading_preferences_user:%') AS canonical_profiles,
                        COUNT(*) FILTER (
                            WHERE key LIKE 'trading_preferences:%'
                              AND key NOT LIKE 'trading_preferences_user:%'
                        ) AS telegram_profiles,
                        COUNT(*) FILTER (WHERE key LIKE 'trade_profile:%') AS trade_profiles
                    FROM runtime_state
                    """,
                ),
                "decision_7d": _query(
                    cur,
                    """
                    SELECT COALESCE(meta->>'asset_class','unknown') AS asset_class,
                           COALESCE(decision,'unknown') AS decision,
                           COALESCE(reason,'unknown') AS reason,
                           COUNT(*) AS rows
                    FROM decision_log
                    WHERE created_at >= NOW()-INTERVAL '7 days'
                    GROUP BY 1,2,3
                    ORDER BY rows DESC
                    LIMIT 80
                    """,
                ),
            }
        finally:
            cur.close()
    finally:
        conn.close()
    print("[readonly_audit] " + json.dumps(result, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
