"""add archived column to signals

Revision ID: 0009_archived_column
Revises: 0008_user_tier_column
Create Date: 2026-01-03

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0009_archived_column"
down_revision = "0008_user_tier_column"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "signals",
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_signals_archived", "signals", ["archived"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_signals_archived", table_name="signals")
    op.drop_column("signals", "archived")
