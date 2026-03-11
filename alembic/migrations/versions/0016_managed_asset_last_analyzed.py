"""Add last_analyzed_at to managed_assets for anti-stagnation queue ordering

Revision ID: 0016_managed_asset_last_analyzed
Revises: 0015_managed_assets
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa

revision = "0016_managed_asset_last_analyzed"
down_revision = "0015_managed_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ADD COLUMN IF NOT EXISTS — idempotent on replay
    op.execute(
        """
        ALTER TABLE managed_assets
        ADD COLUMN IF NOT EXISTS last_analyzed_at TIMESTAMP
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_managed_assets_last_analyzed "
        "ON managed_assets (last_analyzed_at ASC NULLS FIRST)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_managed_assets_last_analyzed")
    op.execute("ALTER TABLE managed_assets DROP COLUMN IF EXISTS last_analyzed_at")
