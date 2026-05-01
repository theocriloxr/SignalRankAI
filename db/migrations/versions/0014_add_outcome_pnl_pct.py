"""Add pnl_pct column to outcomes table.

The Outcome ORM model defines pnl_pct (percentage P&L for the trade outcome)
but the database table created in 0001_init.py never included this column,
causing a ProgrammingError (UndefinedColumn) when the ML training query
SELECTs from the outcomes table via the SQLAlchemy ORM.

Revision ID: 0014_add_outcome_pnl_pct
Revises: 0013_proxy_nodes
Create Date: 2026-05-01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0014_add_outcome_pnl_pct"
down_revision = "0013_proxy_nodes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pnl_pct stores the percentage profit/loss for a closed trade outcome.
    # Nullable to allow existing rows without a computed value.
    op.execute(
        sa.text(
            "ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS pnl_pct FLOAT"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE outcomes DROP COLUMN IF EXISTS pnl_pct"
        )
    )
