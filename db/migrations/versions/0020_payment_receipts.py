"""Add idempotent confirmed-payment receipts.

The table is additive and safe to deploy before the receipt consumer.  No
existing payment or subscription rows are modified.
"""

from alembic import op
import sqlalchemy as sa

revision = "0020_payment_receipts"
down_revision = "0019_user_timezone_privacy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("receipt_number", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="paystack"),
        sa.Column("payment_reference", sa.String(length=128), nullable=False),
        sa.Column("plan", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="NGN"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="paid"),
        sa.Column("payment_date", sa.DateTime(), nullable=False),
        sa.Column("subscription_start", sa.DateTime(), nullable=True),
        sa.Column("subscription_end", sa.DateTime(), nullable=True),
        sa.Column("text_body", sa.Text(), nullable=False, server_default=""),
        sa.Column("html_body", sa.Text(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("receipt_number", name="uq_payment_receipts_number"),
        sa.UniqueConstraint("provider", "payment_reference", name="uq_payment_receipt_provider_reference"),
    )
    op.create_index("ix_payment_receipts_user_id", "payment_receipts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_receipts_user_id", table_name="payment_receipts")
    op.drop_table("payment_receipts")
