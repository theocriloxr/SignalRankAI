"""add execution mode and auto limit to users

Revision ID: 0019_user_execution_mode_and_auto_limit
Revises: 0018_ml_past_training_data
Create Date: 2026-03-14
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0019_user_execution_mode_and_auto_limit"
down_revision = "0018_ml_past_training_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("execution_mode", sa.String(length=16), nullable=False, server_default="manual"))
    op.add_column("users", sa.Column("auto_signals_daily_limit", sa.Integer(), nullable=False, server_default="3"))

    op.create_index("ix_users_execution_mode", "users", ["execution_mode"], unique=False)

    # Normalize any unexpected values
    op.execute("UPDATE users SET execution_mode='manual' WHERE execution_mode IS NULL OR execution_mode=''")



def downgrade() -> None:
    op.drop_index("ix_users_execution_mode", table_name="users")
    op.drop_column("users", "auto_signals_daily_limit")
    op.drop_column("users", "execution_mode")
