"""Make recurring billing opt-in for future accounts without rewriting users.

Revision ID: 0055_user_renewal_default
Revises: 0054_shadow_pending_index
"""
from alembic import op

revision = "0055_user_renewal_default"
down_revision = "0054_shadow_pending_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN auto_renew SET DEFAULT FALSE")


def downgrade() -> None:
    # Restore only the historical default; existing account choices are untouched.
    op.execute("ALTER TABLE users ALTER COLUMN auto_renew SET DEFAULT TRUE")
