"""add user daily drawdown guard

Revision ID: 0020_user_daily_drawdown_guard
Revises: 0019_user_execution_mode_and_auto_limit
Create Date: 2026-03-14
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0020_user_daily_drawdown_guard"
down_revision = "0019_user_execution_mode_and_auto_limit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("max_daily_drawdown_pct", sa.Float(), nullable=False, server_default="8.0"),
    )


def downgrade() -> None:
    op.drop_column("users", "max_daily_drawdown_pct")
