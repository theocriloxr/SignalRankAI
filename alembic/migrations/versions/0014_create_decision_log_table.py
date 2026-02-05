"""Create decision_log table for rejected/skipped tracking

Revision ID: 0014_create_decision_log_table
Revises: 0013_add_premium_until_column
Create Date: 2026-02-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0014_create_decision_log_table"
down_revision = "0013_add_premium_until_column"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decision_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("signal_id", sa.String(length=36), nullable=True),
        sa.Column("asset", sa.String(length=32), nullable=True),
        sa.Column("timeframe", sa.String(length=8), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_decision_log_signal_id", "decision_log", ["signal_id"])
    op.create_index("ix_decision_log_asset", "decision_log", ["asset"])
    op.create_index("ix_decision_log_timeframe", "decision_log", ["timeframe"])
    op.create_index("ix_decision_log_decision", "decision_log", ["decision"])
    op.create_index("ix_decision_log_created_at", "decision_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_decision_log_created_at", table_name="decision_log")
    op.drop_index("ix_decision_log_decision", table_name="decision_log")
    op.drop_index("ix_decision_log_timeframe", table_name="decision_log")
    op.drop_index("ix_decision_log_asset", table_name="decision_log")
    op.drop_index("ix_decision_log_signal_id", table_name="decision_log")
    op.drop_table("decision_log")