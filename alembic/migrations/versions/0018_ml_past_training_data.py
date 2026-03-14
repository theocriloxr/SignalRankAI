"""create ml_past_training_data table

Revision ID: 0018_ml_past_training_data
Revises: 0017_accepted_terms
Create Date: 2026-03-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0018_ml_past_training_data"
down_revision = "0017_accepted_terms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ml_past_training_data",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("signal_id", sa.String(length=36), nullable=False),
        sa.Column("asset", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("entry", sa.Float(), nullable=False),
        sa.Column("stop_loss", sa.Float(), nullable=False),
        sa.Column("take_profit", sa.Text(), nullable=False),
        sa.Column("rr_estimate", sa.Float(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("strength", sa.Float(), nullable=True),
        sa.Column("regime", sa.String(length=32), nullable=True),
        sa.Column("strategy_name", sa.String(length=64), nullable=True),
        sa.Column("ml_probability", sa.Float(), nullable=True),
        sa.Column("outcome_status", sa.String(length=16), nullable=False),
        sa.Column("outcome_r_multiple", sa.Float(), nullable=True),
        sa.Column("outcome_percent", sa.Float(), nullable=True),
        sa.Column("outcome_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("signal_created_at", sa.DateTime(), nullable=True),
        sa.Column("outcome_closed_at", sa.DateTime(), nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("signal_id", name="uq_ml_past_training_data_signal_id"),
    )

    op.create_index("ix_ml_past_training_data_signal_id", "ml_past_training_data", ["signal_id"], unique=True)
    op.create_index("ix_ml_past_training_data_asset", "ml_past_training_data", ["asset"], unique=False)
    op.create_index("ix_ml_past_training_data_timeframe", "ml_past_training_data", ["timeframe"], unique=False)
    op.create_index("ix_ml_past_training_data_outcome_status", "ml_past_training_data", ["outcome_status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ml_past_training_data_outcome_status", table_name="ml_past_training_data")
    op.drop_index("ix_ml_past_training_data_timeframe", table_name="ml_past_training_data")
    op.drop_index("ix_ml_past_training_data_asset", table_name="ml_past_training_data")
    op.drop_index("ix_ml_past_training_data_signal_id", table_name="ml_past_training_data")
    op.drop_table("ml_past_training_data")
