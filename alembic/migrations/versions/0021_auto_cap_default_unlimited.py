"""set auto_signals_daily_limit default to unlimited

Revision ID: 0021_auto_cap_default_unlimited
Revises: 0020_user_daily_drawdown_guard
Create Date: 2026-04-08
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0021_auto_cap_default_unlimited"
down_revision = "0020_user_daily_drawdown_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "auto_signals_daily_limit",
        existing_type=sa.Integer(),
        server_default="-1",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "auto_signals_daily_limit",
        existing_type=sa.Integer(),
        server_default="3",
        existing_nullable=False,
    )
