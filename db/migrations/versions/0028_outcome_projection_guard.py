"""Reconcile outcome projections and enforce one row per signal.

Revision ID: 0028_outcome_projection_guard
Revises: 0027_launch_paper_trading
Create Date: 2026-07-30
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0028_outcome_projection_guard"
down_revision = "0027_launch_paper_trading"
branch_labels = None
depends_on = None


def _exec(sql: str) -> None:
    op.execute(sa.text(sql))


def upgrade() -> None:
    # Migration execution is serialized with any emergency/manual repair job.
    _exec("SELECT pg_advisory_xact_lock(hashtext('signalrank:outcomes:projection-guard:v1'))")

    # Outcome is a mutable projection of the latest lifecycle state. Historical
    # builds could create more than one row per signal. Keep the latest snapshot,
    # repoint notification foreign keys, then remove the stale projections.
    _exec(
        """
        WITH ranked AS (
            SELECT
                id,
                signal_id,
                FIRST_VALUE(id) OVER (
                    PARTITION BY signal_id
                    ORDER BY closed_at DESC NULLS LAST, id DESC
                ) AS keeper_id,
                ROW_NUMBER() OVER (
                    PARTITION BY signal_id
                    ORDER BY closed_at DESC NULLS LAST, id DESC
                ) AS rn
            FROM outcomes
        )
        UPDATE outcome_notifications AS notification
        SET outcome_id = ranked.keeper_id,
            updated_at = NOW()
        FROM ranked
        WHERE ranked.rn > 1
          AND notification.outcome_id = ranked.id
          AND notification.outcome_id <> ranked.keeper_id
        """
    )
    _exec(
        """
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY signal_id
                    ORDER BY closed_at DESC NULLS LAST, id DESC
                ) AS rn
            FROM outcomes
        )
        DELETE FROM outcomes AS outcome
        USING ranked
        WHERE outcome.id = ranked.id
          AND ranked.rn > 1
        """
    )

    # Repair same-name schema drift before creating the guard. PostgreSQL's
    # CREATE INDEX IF NOT EXISTS would otherwise silently keep a non-unique index
    # named uq_outcomes_signal_id and leave the production invariant broken.
    _exec(
        """
        DO $$
        DECLARE
            existing_index_oid OID;
            existing_is_unique BOOLEAN;
        BEGIN
            SELECT i.indexrelid, i.indisunique
            INTO existing_index_oid, existing_is_unique
            FROM pg_index AS i
            JOIN pg_class AS idx ON idx.oid = i.indexrelid
            JOIN pg_class AS tbl ON tbl.oid = i.indrelid
            JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
            WHERE ns.nspname = current_schema()
              AND tbl.relname = 'outcomes'
              AND idx.relname = 'uq_outcomes_signal_id'
            LIMIT 1;

            IF existing_index_oid IS NOT NULL AND existing_is_unique IS FALSE THEN
                EXECUTE 'DROP INDEX ' || existing_index_oid::regclass;
            END IF;
        END
        $$
        """
    )

    # PostgreSQL's runtime readiness gate relies on this exact unique index.
    # IF NOT EXISTS also keeps the migration safe when a correct guard was
    # applied manually before this active Alembic revision reached production.
    _exec(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_outcomes_signal_id "
        "ON outcomes (signal_id)"
    )


def downgrade() -> None:
    _exec("ALTER TABLE outcomes DROP CONSTRAINT IF EXISTS uq_outcomes_signal_id")
    _exec("DROP INDEX IF EXISTS uq_outcomes_signal_id")
