"""Unify rejected signals and pulse metrics into a comprehensive decision_log.

Revision ID: 0046_decision_log
Revises: 0045_mt5_credential_retirement
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0046_decision_log"
down_revision = "0045_mt5_credential_retirement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create the unified decision_log table
    op.create_table(
        "decision_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("signal_id", sa.String(length=36), nullable=True, index=True),
        sa.Column("asset", sa.String(length=32), nullable=False, index=True),
        sa.Column("timeframe", sa.String(length=8), nullable=False, index=True),
        sa.Column("direction", sa.String(length=8), nullable=True),
        sa.Column("layer", sa.String(length=32), nullable=False, index=True),
        sa.Column("decision", sa.String(length=32), nullable=False, index=True),
        sa.Column("reason", sa.String(length=128), nullable=False),
        sa.Column("ml_probability", sa.Float(), nullable=True),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("actual_outcome", sa.String(length=32), nullable=True, index=True),
        sa.Column("outcome_tracked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )

    # 2. Migrate existing data from ml_rejected_signals to decision_log
    op.execute(
        """
        INSERT INTO decision_log (
            signal_id, asset, timeframe, direction, layer, decision, 
            reason, ml_probability, features, actual_outcome, outcome_tracked_at, created_at
        )
        SELECT 
            signal_id, asset, timeframe, direction, 'ml' AS layer, 'rejected' AS decision, 
            rejection_reason AS reason, ml_probability, features, actual_outcome, outcome_tracked_at, created_at
        FROM ml_rejected_signals
        """
    )


def downgrade() -> None:
    op.drop_table("decision_log")
