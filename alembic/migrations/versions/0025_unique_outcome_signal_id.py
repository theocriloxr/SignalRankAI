"""add unique constraint on outcomes.signal_id

Revision ID: 0025_unique_outcome_signal_id
Revises: 0024_add_signal_status
Create Date: 2026-05-30
"""
from alembic import op


revision = "0025_unique_outcome_signal_id"
down_revision = "0024_add_signal_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE outcomes ADD CONSTRAINT uq_outcomes_signal_id UNIQUE (signal_id);")


def downgrade() -> None:
    op.execute("ALTER TABLE outcomes DROP CONSTRAINT IF EXISTS uq_outcomes_signal_id;")
