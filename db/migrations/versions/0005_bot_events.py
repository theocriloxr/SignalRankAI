"""bot events

Revision ID: 0005_bot_events
Revises: 0004_payment_events
Create Date: 2026-01-01

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0005_bot_events"
down_revision = "0004_payment_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bot_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_bot_events_user_id", "bot_events", ["user_id"], unique=False)
    op.create_index("ix_bot_events_event_type", "bot_events", ["event_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_bot_events_event_type", table_name="bot_events")
    op.drop_index("ix_bot_events_user_id", table_name="bot_events")
    op.drop_table("bot_events")
