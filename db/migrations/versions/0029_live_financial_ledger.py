"""Add provider-neutral execution and manually approved payout ledgers.

Revision ID: 0029_live_financial_ledger
Revises: 0028_outcome_projection_guard
Create Date: 2026-07-30
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0029_live_financial_ledger"
down_revision = "0028_outcome_projection_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "processed_webhook_events",
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
    )
    op.add_column(
        "processed_webhook_events",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("processed_webhook_events", sa.Column("last_error", sa.String(512), nullable=True))
    op.add_column("processed_webhook_events", sa.Column("processed_at", sa.DateTime(), nullable=True))
    op.add_column(
        "processed_webhook_events",
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_processed_webhook_events_status", "processed_webhook_events", ["status"])

    op.create_table(
        "broker_executions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("signal_id", sa.String(36), sa.ForeignKey("signals.signal_id"), nullable=True),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("account_ref", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("provider_order_id", sa.String(128), nullable=True),
        sa.Column("provider_client_order_id", sa.String(64), nullable=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("stop_loss", sa.Float(), nullable=False),
        sa.Column("take_profit", sa.Float(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="reserved"),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("realized_pnl_pct", sa.Float(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("tier_at_execution", sa.String(16), nullable=False, server_default="vip"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("provider", "idempotency_key", name="uq_broker_execution_provider_key"),
    )
    op.create_index("ix_broker_executions_user_id", "broker_executions", ["user_id"])
    op.create_index("ix_broker_executions_signal_id", "broker_executions", ["signal_id"])
    op.create_index("ix_broker_executions_provider", "broker_executions", ["provider"])
    op.create_index("ix_broker_executions_status", "broker_executions", ["status"])
    op.create_index("ix_broker_executions_created_at", "broker_executions", ["created_at"])
    op.create_index("ix_broker_executions_closed_at", "broker_executions", ["closed_at"])

    op.create_table(
        "payout_accounts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="NGN"),
        sa.Column("bank_code", sa.String(16), nullable=False),
        sa.Column("bank_name", sa.String(128), nullable=False),
        sa.Column("account_number_encrypted", sa.String(512), nullable=False),
        sa.Column("account_last4", sa.String(4), nullable=False),
        sa.Column("account_name", sa.String(160), nullable=False),
        sa.Column("recipient_code_encrypted", sa.String(512), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("user_id", "currency", name="uq_payout_account_user_currency"),
    )
    op.create_index("ix_payout_accounts_user_id", "payout_accounts", ["user_id"])

    op.create_table(
        "payout_requests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("reference", sa.String(128), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("payout_account_id", sa.BigInteger(), sa.ForeignKey("payout_accounts.id"), nullable=False),
        sa.Column("amount_kobo", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="NGN"),
        sa.Column("status", sa.String(24), nullable=False, server_default="requested"),
        sa.Column("reason", sa.String(256), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("approved_by_telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("provider_transfer_code", sa.String(128), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("failure_code", sa.String(128), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("reference", name="uq_payout_request_reference"),
    )
    op.create_index("ix_payout_requests_user_id", "payout_requests", ["user_id"])
    op.create_index("ix_payout_requests_status", "payout_requests", ["status"])
    op.create_index("ix_payout_requests_provider_transfer_code", "payout_requests", ["provider_transfer_code"])


def downgrade() -> None:
    op.drop_table("payout_requests")
    op.drop_table("payout_accounts")
    op.drop_table("broker_executions")
    op.drop_index("ix_processed_webhook_events_status", table_name="processed_webhook_events")
    op.drop_column("processed_webhook_events", "updated_at")
    op.drop_column("processed_webhook_events", "processed_at")
    op.drop_column("processed_webhook_events", "last_error")
    op.drop_column("processed_webhook_events", "attempt_count")
    op.drop_column("processed_webhook_events", "status")
