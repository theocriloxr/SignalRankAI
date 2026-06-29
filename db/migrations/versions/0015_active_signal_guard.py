"""Add active signal uniqueness and hot-path indexes.

Revision ID: 0015_active_signal_guard
Revises: 0014_add_outcome_pnl_pct
Create Date: 2026-06-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0015_active_signal_guard"
down_revision = "0014_add_outcome_pnl_pct"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_signals_active_thesis",
        "signals",
        ["asset", "direction", "timeframe"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_signals_asset_status_created_at",
        "signals",
        ["asset", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_outcomes_signal_status_closed_at",
        "outcomes",
        ["signal_id", "status", "closed_at"],
        unique=False,
    )
    op.create_index(
        "ix_signal_deliveries_user_sent_ok_delivered_at",
        "signal_deliveries",
        ["user_id", "sent_ok", "delivered_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_signal_deliveries_user_sent_ok_delivered_at", table_name="signal_deliveries")
    op.drop_index("ix_outcomes_signal_status_closed_at", table_name="outcomes")
    op.drop_index("ix_signals_asset_status_created_at", table_name="signals")
    op.drop_index("ix_signals_active_thesis", table_name="signals")