#!/usr/bin/env python3
"""Inspect or reconcile legacy near-identical active SignalRankAI theses.

Dry-run is the default. ``--apply`` keeps the earliest/proof-backed canonical
trade idea and retires later near-identical rows created inside the configured
thesis window. It never deletes signals, deliveries, outcomes, or audit history.

This script repairs rows created before v1.3.6.7. Normal runtime admission now
uses PostgreSQL advisory locks plus semantic near-entry deduplication.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import create_engine, text


def _sync_url(raw: str) -> str:
    return (
        raw.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
        .replace("postgres://", "postgresql+psycopg2://", 1)
    )


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _proof_time(row: dict[str, Any]) -> datetime:
    return row.get("first_delivery_at") or row.get("created_at") or datetime.max


def _is_near(first: dict[str, Any], second: dict[str, Any], *, tolerance: float, window: timedelta) -> bool:
    created_a = first.get("created_at")
    created_b = second.get("created_at")
    if not created_a or not created_b or abs(created_b - created_a) > window:
        return False
    entry_a = _float(first.get("entry"))
    entry_b = _float(second.get("entry"))
    if entry_a <= 0 or entry_b <= 0:
        return False
    gap = abs(entry_a - entry_b) / max(abs(entry_a), abs(entry_b), 1e-9)
    return gap <= tolerance


ACTIVE_SQL = text(
    """
    SELECT
        s.signal_id, s.asset, s.direction, COALESCE(s.strategy_name, 'unknown') AS strategy_name,
        s.timeframe, s.entry, s.created_at, s.status,
        MIN(COALESCE(d.delivery_confirmed_at, d.delivered_at_utc, d.delivered_at))
            FILTER (WHERE d.sent_ok IS TRUE AND d.telegram_chat_id IS NOT NULL
                    AND d.telegram_message_id IS NOT NULL) AS first_delivery_at,
        COUNT(d.id) FILTER (WHERE d.sent_ok IS TRUE AND d.telegram_chat_id IS NOT NULL
                            AND d.telegram_message_id IS NOT NULL) AS confirmed_deliveries,
        LOWER(COALESCE(o.status, 'pending')) AS outcome_status
    FROM signals s
    LEFT JOIN signal_deliveries d ON d.signal_id = s.signal_id
    LEFT JOIN outcomes o ON o.signal_id = s.signal_id
    WHERE COALESCE(s.archived, FALSE) IS FALSE
      AND COALESCE(s.expired, FALSE) IS FALSE
      AND LOWER(COALESCE(s.status, 'active')) IN ('active', 'pending', 'entered', 'tp1', 'tp2')
      AND s.created_at >= :cutoff
    GROUP BY s.signal_id, s.asset, s.direction, s.strategy_name, s.timeframe,
             s.entry, s.created_at, s.status, o.status
    ORDER BY s.asset, s.direction, COALESCE(s.strategy_name, 'unknown'),
             s.created_at ASC, s.signal_id ASC
    """
)


APPLY_SIGNAL_SQL = text(
    """
    UPDATE signals
    SET status = 'superseded_duplicate', archived = TRUE, expired = TRUE
    WHERE signal_id = :duplicate_signal_id
    """
)

APPLY_OUTCOME_SQL = text(
    """
    UPDATE outcomes
    SET status = 'cancelled', canonical_outcome = 'cancelled',
        r_multiple = NULL, percent = NULL, pnl_pct = NULL,
        closed_at = COALESCE(closed_at, NOW()),
        performance_inclusion_status = 'excluded',
        performance_exclusion_reason = 'duplicate_thesis_delivery_within_cooldown',
        calculation_policy_version = 'duplicate-repair-v1367',
        meta = (COALESCE(meta::jsonb, '{}'::jsonb) || jsonb_build_object(
            'systemic_repair', 'v1.3.6.7_duplicate_reconciliation',
            'duplicate_of', CAST(:canonical_signal_id AS text),
            'repaired_at', NOW()::text
        ))::json
    WHERE signal_id = :duplicate_signal_id
      AND LOWER(COALESCE(status, 'pending')) IN
          ('pending', 'active', 'entered', 'entry', 'tp1', 'tp2', 'partial_win', 'partial_win_be')
      AND corrected_at IS NULL
    """
)

APPLY_LIFECYCLE_SQL = text(
    """
    UPDATE signal_lifecycles
    SET state = 'SUPERSEDED_DUPLICATE',
        expired_at = COALESCE(expired_at, NOW()),
        closed_at = COALESCE(closed_at, NOW()),
        terminal_event_type = 'duplicate_superseded',
        terminal_evidence = (COALESCE(terminal_evidence::jsonb, '{}'::jsonb) || jsonb_build_object(
            'duplicate_of', CAST(:canonical_signal_id AS text),
            'systemic_repair', 'v1.3.6.7_duplicate_reconciliation'
        ))::json,
        updated_at = NOW()
    WHERE signal_id = :duplicate_signal_id
      AND LOWER(COALESCE(state, 'watching_for_entry')) NOT IN
          ('tp3', 'sl', 'closed', 'expired', 'cancelled', 'superseded_duplicate')
    """
)

APPLY_MONITORING_SQL = text(
    """
    UPDATE user_signal_monitoring
    SET status = 'stopped', stopped_at = COALESCE(stopped_at, NOW()),
        realized_outcome = 'duplicate_excluded', realized_r = NULL, updated_at = NOW()
    WHERE signal_id = :duplicate_signal_id
      AND LOWER(COALESCE(status, 'auto_continue')) IN ('auto_continue', 'continued')
    """
)

AUDIT_SQL = text(
    """
    INSERT INTO admin_events(event_type, actor_telegram_user_id, details, created_at)
    VALUES (
        'ops_semantic_signal_dedupe', NULL,
        json_build_object(
            'duplicate_signal_id', CAST(:duplicate_signal_id AS text),
            'canonical_signal_id', CAST(:canonical_signal_id AS text),
            'asset', CAST(:asset AS text),
            'direction', CAST(:direction AS text),
            'strategy_name', CAST(:strategy_name AS text),
            'entry_gap_pct', CAST(:entry_gap_pct AS double precision),
            'rows_deleted', 0,
            'release', 'v1.3.6.7'
        ),
        NOW()
    )
    """
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit the non-destructive reconciliation")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--hours", type=int, default=int(os.getenv("SIGNAL_THESIS_DEDUP_HOURS", "4") or 4))
    parser.add_argument(
        "--entry-tolerance",
        type=float,
        default=float(os.getenv("SIGNAL_SEMANTIC_ENTRY_TOLERANCE_PCT", "0.003") or 0.003),
        help="Relative decimal tolerance; 0.003 means 0.3 percent",
    )
    parser.add_argument("--output", default="", help="Optional JSON report path")
    args = parser.parse_args()

    raw_url = str(os.getenv("DATABASE_URL") or "").strip()
    if not raw_url:
        raise SystemExit("DATABASE_URL is required")
    window = timedelta(hours=max(1, int(args.hours)))
    tolerance = max(0.0001, min(0.05, float(args.entry_tolerance)))
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(1, int(args.days)))

    engine = create_engine(_sync_url(raw_url), pool_pre_ping=True)
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry_run",
        "window_hours": int(args.hours),
        "entry_tolerance": tolerance,
        "duplicates": [],
        "applied": 0,
        "rows_deleted": 0,
    }

    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('signalrank:semantic_duplicate_repair:v1367'))"))
        rows = [dict(row._mapping) for row in conn.execute(ACTIVE_SQL, {"cutoff": cutoff})]
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[(
                str(row.get("asset") or "").upper(),
                str(row.get("direction") or "").lower(),
                str(row.get("strategy_name") or "unknown").lower(),
            )].append(row)

        for (_asset, _direction, _strategy), candidates in grouped.items():
            canonicals: list[dict[str, Any]] = []
            candidates.sort(key=lambda row: (
                0 if int(row.get("confirmed_deliveries") or 0) > 0 else 1,
                _proof_time(row),
                row.get("created_at") or datetime.max,
                str(row.get("signal_id")),
            ))
            for candidate in candidates:
                canonical = next(
                    (item for item in canonicals if _is_near(item, candidate, tolerance=tolerance, window=window)),
                    None,
                )
                if canonical is None:
                    canonicals.append(candidate)
                    continue
                gap = abs(_float(canonical["entry"]) - _float(candidate["entry"])) / max(
                    abs(_float(canonical["entry"])), abs(_float(candidate["entry"])), 1e-9
                )
                item = {
                    "duplicate_signal_id": str(candidate["signal_id"]),
                    "canonical_signal_id": str(canonical["signal_id"]),
                    "asset": candidate["asset"],
                    "direction": candidate["direction"],
                    "strategy_name": candidate["strategy_name"],
                    "duplicate_timeframe": candidate["timeframe"],
                    "canonical_timeframe": canonical["timeframe"],
                    "entry_gap_pct": round(gap * 100.0, 8),
                    "confirmed_deliveries": int(candidate.get("confirmed_deliveries") or 0),
                    "outcome_status": candidate.get("outcome_status"),
                }
                report["duplicates"].append(item)
                if args.apply:
                    params = dict(item)
                    conn.execute(APPLY_SIGNAL_SQL, params)
                    conn.execute(APPLY_OUTCOME_SQL, params)
                    conn.execute(APPLY_LIFECYCLE_SQL, params)
                    conn.execute(APPLY_MONITORING_SQL, params)
                    conn.execute(AUDIT_SQL, params)
                    report["applied"] += 1

    rendered = json.dumps(report, indent=2, default=str, sort_keys=True)
    print(rendered)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
