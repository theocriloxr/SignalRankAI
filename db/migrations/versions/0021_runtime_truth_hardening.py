"""Repair runtime-truth schema drift and add proof-gate indexes.

Revision ID: 0021_runtime_truth_hardening
Revises: 0020_payment_receipts
Create Date: 2026-07-25
"""

from alembic import op

revision = "0021_runtime_truth_hardening"
down_revision = "0020_payment_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE decision_log ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW()")
    op.execute("ALTER TABLE decision_log ADD COLUMN IF NOT EXISTS meta JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("CREATE INDEX IF NOT EXISTS ix_decision_log_created_at ON decision_log(created_at)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_signal_deliveries_live_proof "
        "ON signal_deliveries(signal_id, sent_ok, delivery_state) "
        "WHERE sent_ok IS TRUE"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_signals_open_expiry "
        "ON signals(expired, archived, expires_at, asset, direction)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_signals_open_expiry")
    op.execute("DROP INDEX IF EXISTS ix_signal_deliveries_live_proof")
    # Repaired audit columns are retained to avoid destructive rollback.
