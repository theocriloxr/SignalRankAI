"""Re-verify the active signal uniqueness guard on upgraded databases.

Revision ID: 0022_active_guard_reconcile
Revises: 0021_runtime_truth_hardening
Create Date: 2026-07-26

This forward-only hardening migration protects environments that were stamped,
manually repaired, or upgraded with an older copy of revision 0015.  It keeps
all historical rows and changes only duplicate ``active`` statuses.
"""
from __future__ import annotations

import logging

from alembic import op
import sqlalchemy as sa


revision = "0022_active_guard_reconcile"
down_revision = "0021_runtime_truth_hardening"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


_RECONCILE_SQL = """
WITH active_candidates AS (
    SELECT
        s.signal_id,
        s.asset,
        s.direction,
        s.timeframe,
        s.created_at,
        CASE WHEN EXISTS (
            SELECT 1
            FROM outcomes o
            WHERE o.signal_id = s.signal_id
              AND LOWER(COALESCE(o.status, '')) IN ('active', 'tp1', 'tp2')
        ) THEN 1 ELSE 0 END AS has_open_outcome,
        CASE WHEN EXISTS (
            SELECT 1
            FROM signal_deliveries d
            WHERE d.signal_id = s.signal_id
              AND COALESCE(d.sent_ok, FALSE) IS TRUE
              AND d.telegram_chat_id IS NOT NULL
              AND d.telegram_message_id IS NOT NULL
        ) THEN 1 ELSE 0 END AS has_delivery_proof,
        COALESCE(deliveries.delivery_count, 0) AS delivery_count
    FROM signals s
    LEFT JOIN (
        SELECT signal_id, COUNT(*)::bigint AS delivery_count
        FROM signal_deliveries
        GROUP BY signal_id
    ) deliveries ON deliveries.signal_id = s.signal_id
    WHERE s.status = 'active'
), ranked AS (
    SELECT
        signal_id,
        asset,
        direction,
        timeframe,
        has_open_outcome,
        has_delivery_proof,
        delivery_count,
        ROW_NUMBER() OVER (
            PARTITION BY asset, direction, timeframe
            ORDER BY
                has_open_outcome DESC,
                has_delivery_proof DESC,
                delivery_count DESC,
                created_at DESC NULLS LAST,
                signal_id DESC
        ) AS row_num,
        FIRST_VALUE(signal_id) OVER (
            PARTITION BY asset, direction, timeframe
            ORDER BY
                has_open_outcome DESC,
                has_delivery_proof DESC,
                delivery_count DESC,
                created_at DESC NULLS LAST,
                signal_id DESC
        ) AS canonical_signal_id
    FROM active_candidates
), duplicates AS (
    SELECT * FROM ranked WHERE row_num > 1
), audit AS (
    INSERT INTO admin_events (
        event_type,
        actor_telegram_user_id,
        details,
        created_at
    )
    SELECT
        'migration_active_signal_dedupe',
        NULL,
        json_build_object(
            'revision', '0022_active_guard_reconcile',
            'superseded_signal_id', d.signal_id,
            'canonical_signal_id', d.canonical_signal_id,
            'asset', d.asset,
            'direction', d.direction,
            'timeframe', d.timeframe,
            'had_open_outcome', (d.has_open_outcome = 1),
            'had_delivery_proof', (d.has_delivery_proof = 1),
            'delivery_count', d.delivery_count,
            'action', 'status_changed_to_superseded',
            'rows_deleted', 0
        ),
        NOW()
    FROM duplicates d
    RETURNING 1
)
UPDATE signals s
SET status = 'superseded'
FROM duplicates d
WHERE s.signal_id = d.signal_id
RETURNING s.signal_id
"""


def upgrade() -> None:
    bind = op.get_bind()
    if str(bind.dialect.name or "").lower() == "postgresql":
        bind.execute(
            sa.text(
                "SELECT pg_advisory_xact_lock(hashtext('signalrank:active_signal_guard'))"
            )
        )
        result = bind.execute(sa.text(_RECONCILE_SQL))
        rows = result.fetchall() if getattr(result, "returns_rows", False) else []
        if rows:
            logger.warning(
                "Forward guard reconciled %s duplicate active signal row(s).",
                len(rows),
            )

    # Replace a same-named non-unique/manual index before enforcing the real
    # contract.  The DO block is harmless when the correct index already exists.
    op.execute(
        """
        DO $$
        DECLARE current_definition text;
        BEGIN
            SELECT indexdef INTO current_definition
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND indexname = 'ix_signals_active_thesis';

            IF current_definition IS NOT NULL
               AND current_definition NOT ILIKE 'CREATE UNIQUE INDEX%'
            THEN
                EXECUTE 'DROP INDEX IF EXISTS ix_signals_active_thesis';
            END IF;
        END $$
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_signals_active_thesis
        ON signals (asset, direction, timeframe)
        WHERE status = 'active'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_signal_deliveries_user_sent_ok_delivered_at
        ON signal_deliveries (user_id, sent_ok, delivered_at)
        """
    )


def downgrade() -> None:
    # The guard was introduced in 0015.  Downgrading 0022 must not remove it.
    pass
