"""canonical web paper-trading receipt provenance

Revision ID: 0040_cross_channel_paper_receipt
Revises: 0039_web_signup_acquisition
"""
from __future__ import annotations

from alembic import op

revision = "0040_cross_channel_paper_receipt"
down_revision = "0039_web_signup_acquisition"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A paper attempt may originate from either strict Telegram delivery proof
    # or an idempotent gated web receipt.  Telegram delivery_id therefore stays
    # available when it exists but is no longer the only valid provenance key.
    op.execute(
        "ALTER TABLE paper_trade_attempts "
        "ALTER COLUMN delivery_id DROP NOT NULL"
    )
    op.execute(
        "ALTER TABLE paper_trade_attempts "
        "ADD COLUMN IF NOT EXISTS receipt_channel VARCHAR(16) NOT NULL DEFAULT 'telegram'"
    )
    op.execute(
        "ALTER TABLE paper_trade_attempts "
        "ADD COLUMN IF NOT EXISTS receipt_reference VARCHAR(64)"
    )
    op.execute(
        """
        UPDATE paper_trade_attempts
        SET receipt_channel='telegram',
            receipt_reference=COALESCE(receipt_reference, delivery_id::text)
        WHERE receipt_reference IS NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_paper_trade_attempt_receipt "
        "ON paper_trade_attempts(user_id,receipt_channel,receipt_reference)"
    )


def downgrade() -> None:
    # Downgrade can only restore the Telegram-only invariant after removing
    # cross-channel attempts that cannot reference signal_deliveries.
    op.execute("DELETE FROM paper_trade_attempts WHERE delivery_id IS NULL")
    op.execute("DROP INDEX IF EXISTS ix_paper_trade_attempt_receipt")
    op.execute("ALTER TABLE paper_trade_attempts DROP COLUMN IF EXISTS receipt_reference")
    op.execute("ALTER TABLE paper_trade_attempts DROP COLUMN IF EXISTS receipt_channel")
    op.execute(
        "ALTER TABLE paper_trade_attempts "
        "ALTER COLUMN delivery_id SET NOT NULL"
    )
