"""user tier column

Revision ID: 0008_user_tier_column
Revises: 0007_market_data_cache
Create Date: 2026-01-03

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008_user_tier_column"
down_revision = "0007_market_data_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("tier", sa.String(length=16), nullable=False, server_default=sa.text("'free'")),
    )
    op.create_index("ix_users_tier", "users", ["tier"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_tier", table_name="users")
    op.drop_column("users", "tier")
