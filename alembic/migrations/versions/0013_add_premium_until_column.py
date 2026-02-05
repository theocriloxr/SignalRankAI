"""Add premium_until column to users (safe)

Revision ID: 0013_add_premium_until_column
Revises: 0012_ml_rejection_and_referrals
Create Date: 2026-02-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0013_add_premium_until_column"
down_revision = "0012_ml_rejection_and_referrals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add column if it does not exist (idempotent for prod hotfixes).
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS premium_until TIMESTAMP")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS premium_until")
