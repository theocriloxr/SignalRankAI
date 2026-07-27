"""Repair Signal ORM runtime columns and reassert the active-thesis guard.

Revision ID: 0023_signal_runtime_schema
Revises: 0022_active_guard_reconcile
Create Date: 2026-07-27

The clean Alembic chain historically omitted ``signals.mfe_pct`` and
``signals.mae_pct`` even though both columns are part of the canonical
``Signal`` ORM model and are selected by the outcome tracker.  This forward
repair is intentionally idempotent for clean, legacy, and partially prepared
PostgreSQL databases.  It also recreates the partial unique index using the
canonical definition after reconciling any unexpected duplicate active rows.
"""
from __future__ import annotations

import logging

from alembic import op
import sqlalchemy as sa


revision = "0023_signal_runtime_schema"
down_revision = "0022_active_guard_reconcile"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


_RECONCILE_DUPLICATES_SQL = """
WITH ranked AS (
    SELECT
        signal_id,
        ROW_NUMBER() OVER (
            PARTITION BY asset, direction, timeframe
            ORDER BY created_at DESC NULLS LAST, signal_id DESC
        ) AS row_num
    FROM signals
    WHERE status = 'active'
)
UPDATE signals AS s
SET status = 'superseded'
FROM ranked AS r
WHERE s.signal_id = r.signal_id
  AND r.row_num > 1
RETURNING s.signal_id
"""


def _ensure_columns() -> None:
    bind = op.get_bind()
    dialect = str(bind.dialect.name or "").lower()

    if dialect == "postgresql":
        bind.execute(sa.text("ALTER TABLE signals ADD COLUMN IF NOT EXISTS mfe_pct DOUBLE PRECISION"))
        bind.execute(sa.text("ALTER TABLE signals ADD COLUMN IF NOT EXISTS mae_pct DOUBLE PRECISION"))
        bind.execute(
            sa.text(
                "ALTER TABLE signals ADD COLUMN IF NOT EXISTS "
                "performance_version INTEGER NOT NULL DEFAULT 2"
            )
        )
        bind.execute(sa.text("UPDATE signals SET performance_version = 2 WHERE performance_version IS NULL"))
        bind.execute(sa.text("ALTER TABLE signals ALTER COLUMN performance_version SET DEFAULT 2"))
        bind.execute(sa.text("ALTER TABLE signals ALTER COLUMN performance_version SET NOT NULL"))
        return

    inspector = sa.inspect(bind)
    columns = {
        str(column.get("name") or "").lower()
        for column in inspector.get_columns("signals")
    }
    if "mfe_pct" not in columns:
        op.add_column("signals", sa.Column("mfe_pct", sa.Float(), nullable=True))
    if "mae_pct" not in columns:
        op.add_column("signals", sa.Column("mae_pct", sa.Float(), nullable=True))
    if "performance_version" not in columns:
        op.add_column(
            "signals",
            sa.Column(
                "performance_version",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("2"),
            ),
        )
    bind.execute(sa.text("UPDATE signals SET performance_version = 2 WHERE performance_version IS NULL"))


def _reassert_active_guard() -> None:
    bind = op.get_bind()
    dialect = str(bind.dialect.name or "").lower()

    if dialect == "postgresql":
        bind.execute(
            sa.text(
                "SELECT pg_advisory_xact_lock(hashtext('signalrank:active_signal_guard'))"
            )
        )

    result = bind.execute(sa.text(_RECONCILE_DUPLICATES_SQL))
    rows = result.fetchall() if getattr(result, "returns_rows", False) else []
    if rows:
        logger.warning(
            "Runtime-schema guard reconciled %s duplicate active signal row(s).",
            len(rows),
        )

    op.execute("DROP INDEX IF EXISTS ix_signals_active_thesis")
    op.execute(
        """
        CREATE UNIQUE INDEX ix_signals_active_thesis
        ON signals (asset, direction, timeframe)
        WHERE status = 'active'
        """
    )


def upgrade() -> None:
    _ensure_columns()
    _reassert_active_guard()


def downgrade() -> None:
    # Forward-only runtime contract repair.  Revision 0022 and the application
    # both depend on the active guard, while the ORM depends on these columns.
    pass
