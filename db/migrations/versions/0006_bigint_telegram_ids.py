"""telegram ids bigint

Revision ID: 0006_bigint_telegram_ids
Revises: 0005_bot_events
Create Date: 2026-01-01

"""

from alembic import op
import sqlalchemy as sa


revision = "0006_bigint_telegram_ids"
down_revision = "0005_bot_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Telegram user IDs can exceed 32-bit int; store them as BIGINT.
    op.alter_column(
        "users",
        "telegram_user_id",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )
    op.alter_column(
        "admin_events",
        "actor_telegram_user_id",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "admin_events",
        "actor_telegram_user_id",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
    )
    op.alter_column(
        "users",
        "telegram_user_id",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
    )
