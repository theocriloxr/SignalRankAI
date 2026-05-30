"""add status column to signals table

Revision ID: 0024_add_signal_status
Revises: 0023_outcome_truth_and_delivery_state
Create Date: 2026-05-30
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0024_add_signal_status"
down_revision = "0023_outcome_truth_and_delivery_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add status column to signals for shadow tracking and analysis
    op.execute("ALTER TABLE signals ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'issued';")
    op.execute("CREATE INDEX IF NOT EXISTS ix_signals_status ON signals(status);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_signals_status;")
    op.execute("ALTER TABLE signals DROP COLUMN IF EXISTS status;")
