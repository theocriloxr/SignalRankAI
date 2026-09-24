#!/usr/bin/env python3
"""Read-only aggregate runtime audit for staging/production certification.

This script never mutates data and never emits secrets or per-user identifiers.
It is intended for one-off Railway certification services.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
                    WHERE d.delivered_at >= NOW()-INTERVAL '7 days'
                    GROUP BY 1 ORDER BY 1
                    """,
                ),
                "delivery_failures_7d": _query(
                    cur,
                    """
                    SELECT
                        COALESCE(s.asset_class,'unknown') AS asset_class,
                        lower(COALESCE(d.delivery_state,'unknown')) AS delivery_state,
                        CASE
                            WHEN d.sent_ok IS TRUE THEN 'sent_ok'
                            WHEN d.last_error IS NULL OR btrim(d.last_error) = '' THEN 'no_error_recorded'
                            WHEN lower(d.last_error) LIKE '%blocked%' THEN 'telegram_blocked'
                            WHEN lower(d.last_error) LIKE '%chat not found%' OR lower(d.last_error) LIKE '%chat not accessible%' THEN 'telegram_chat_unreachable'
                            WHEN lower(d.last_error) LIKE '%deactivated%' THEN 'telegram_user_deactivated'
                            WHEN lower(d.last_error) LIKE '%retry after%' OR lower(d.last_error) LIKE '%too many requests%' OR lower(d.last_error) LIKE '%rate limit%' THEN 'telegram_rate_limited'
                            WHEN lower(d.last_error) LIKE '%timeout%' OR lower(d.last_error) LIKE '%timed out%' THEN 'telegram_timeout'
                            WHEN lower(d.last_error) LIKE '%bad request%' THEN 'telegram_bad_request'
                            WHEN lower(d.last_error) LIKE '%database%' OR lower(d.last_error) LIKE '%sql%' OR lower(d.last_error) LIKE '%asyncpg%' THEN 'database_error'
                            WHEN lower(d.last_error) LIKE '%proof%' THEN 'delivery_proof_error'
                            WHEN lower(d.last_error) = 'asset_delivery_locked' THEN 'asset_delivery_locked'
                            WHEN lower(d.last_error) = 'asset_lock_check_failed_closed' THEN 'asset_lock_check_failed_closed'
                            WHEN lower(d.last_error) = 'final_validation_timeout' THEN 'final_validation_timeout'
                            WHEN lower(d.last_error) LIKE 'final_validation_error:%' THEN 'final_validation_error'
                            WHEN lower(d.last_error) LIKE 'live_price_unavailable:%' OR lower(d.last_error) = 'live_price_unavailable' THEN 'freshness_live_price_unavailable'
                            WHEN lower(d.last_error) LIKE 'price_drift:%' OR lower(d.last_error) LIKE 'final_entry_drift:%' THEN 'freshness_entry_drift'
                            WHEN lower(d.last_error) LIKE '%tp1%hit%' OR lower(d.last_error) LIKE '%target%hit%' THEN 'freshness_target_already_hit'
                            WHEN lower(d.last_error) LIKE '%stop%hit%' OR lower(d.last_error) LIKE '%sl%hit%' THEN 'freshness_stop_already_hit'
                            WHEN lower(d.last_error) LIKE '%reward%risk%' OR lower(d.last_error) LIKE '%rr_%' OR lower(d.last_error) LIKE '%rr %' THEN 'freshness_reward_risk'
                            WHEN lower(d.last_error) LIKE '%stale%' OR lower(d.last_error) LIKE '%age%' OR lower(d.last_error) LIKE '%queue%' THEN 'freshness_stale_or_queue'
                            WHEN lower(d.last_error) LIKE '%missing_generated_at%' OR lower(d.last_error) LIKE '%missing_created_at%' THEN 'freshness_missing_timestamp'
                            ELSE 'other_error'
                        END AS error_class,
                        COUNT(*) AS rows,
                        COUNT(*) FILTER (WHERE d.telegram_chat_id IS NULL) AS missing_chat_id,
                        COUNT(*) FILTER (WHERE d.telegram_message_id IS NULL) AS missing_message_id,
                        MAX(d.attempt_count) AS max_attempts
                    FROM signal_deliveries d
                    JOIN signals s ON s.signal_id=d.signal_id
                    WHERE d.delivered_at >= NOW()-INTERVAL '7 days'
                    GROUP BY 1,2,3
                    ORDER BY rows DESC, 1,2,3
                    LIMIT 100
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
                "profile_linkage": _query(
                    cur,
                    """
                    SELECT
                        COUNT(*) AS total_users,
                        COUNT(*) FILTER (WHERE u.telegram_user_id IS NOT NULL) AS linked_telegram_users,
                        COUNT(*) FILTER (
                            WHERE u.telegram_user_id IS NOT NULL
                              AND EXISTS (
                                  SELECT 1 FROM runtime_state r
                                  WHERE r.key = 'trading_preferences:' || u.telegram_user_id::text
                              )
                        ) AS linked_with_telegram_profile,
                        COUNT(*) FILTER (
                            WHERE u.telegram_user_id IS NOT NULL
                              AND EXISTS (
                                  SELECT 1 FROM runtime_state r
                                  WHERE r.key = 'trading_preferences_user:' || u.id::text
                              )
                        ) AS linked_with_canonical_profile
                    FROM users u
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
