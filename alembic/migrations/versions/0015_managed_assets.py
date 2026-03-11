"""Create managed_assets table for admin-pinned asset universe

Revision ID: 0015_managed_assets
Revises: 0014_create_decision_log_table
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0015_managed_assets"
down_revision = "0014_create_decision_log_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use raw SQL with IF NOT EXISTS so this migration is safe to re-run even if
    # the table was already created by a previous partial deployment.  Alembic's
    # op.create_table() has no IF NOT EXISTS support and would crash on replay,
    # causing an infinite Railway restart loop.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS managed_assets (
            id          SERIAL PRIMARY KEY,
            symbol      VARCHAR(32)  NOT NULL,
            asset_type  VARCHAR(16)  NOT NULL DEFAULT 'crypto',
            is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
            added_by    BIGINT,
            note        VARCHAR(256),
            created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMP    NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_managed_assets_symbol "
        "ON managed_assets (symbol)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_managed_assets_is_active "
        "ON managed_assets (is_active)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_managed_assets_is_active")
    op.execute("DROP INDEX IF EXISTS ix_managed_assets_symbol")
    op.execute("DROP TABLE IF EXISTS managed_assets")
