"""payment events

Revision ID: 0004_payment_events
Revises: 0003_runtime_state
Create Date: 2026-01-01

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0004_payment_events"
down_revision = "0003_runtime_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="subscription"),
        sa.Column("tier", sa.String(length=32), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("plan_code", sa.String(length=128), nullable=True),
        sa.Column("amount_ngn", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("paystack_reference", sa.String(length=128), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_payment_events_user_id", "payment_events", ["user_id"], unique=False)
    op.create_index("ix_payment_events_kind", "payment_events", ["kind"], unique=False)
    op.create_index("ix_payment_events_tier", "payment_events", ["tier"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_payment_events_tier", table_name="payment_events")
    op.drop_index("ix_payment_events_kind", table_name="payment_events")
    op.drop_index("ix_payment_events_user_id", table_name="payment_events")
    op.drop_table("payment_events")
