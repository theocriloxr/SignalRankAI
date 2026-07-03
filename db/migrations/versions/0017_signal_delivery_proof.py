"""Signal delivery Telegram proof fields.

Revision ID: 0017_signal_delivery_proof
Revises: 0016_signal_profile_metadata
Create Date: 2026-07-04
"""

from alembic import op


revision = "0017_signal_delivery_proof"
down_revision = "0016_signal_profile_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS delivery_state VARCHAR(16) NOT NULL DEFAULT 'reserved'")
    op.execute("ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS dispatch_started_at TIMESTAMP")
    op.execute("ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS telegram_send_started_at TIMESTAMP")
    op.execute("ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS delivery_confirmed_at TIMESTAMP")
    op.execute("ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS telegram_chat_id BIGINT")
    op.execute("ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS telegram_message_id BIGINT")
    op.execute("ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS telegram_api_result JSON DEFAULT '{}'::json")
    op.execute("CREATE INDEX IF NOT EXISTS ix_signal_deliveries_state ON signal_deliveries(delivery_state)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_signal_deliveries_telegram_msg ON signal_deliveries(telegram_chat_id, telegram_message_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_signal_deliveries_telegram_msg")
    op.execute("DROP INDEX IF EXISTS ix_signal_deliveries_state")
    op.execute("ALTER TABLE signal_deliveries DROP COLUMN IF EXISTS telegram_api_result")
    op.execute("ALTER TABLE signal_deliveries DROP COLUMN IF EXISTS telegram_message_id")
    op.execute("ALTER TABLE signal_deliveries DROP COLUMN IF EXISTS telegram_chat_id")
    op.execute("ALTER TABLE signal_deliveries DROP COLUMN IF EXISTS delivery_confirmed_at")
    op.execute("ALTER TABLE signal_deliveries DROP COLUMN IF EXISTS telegram_send_started_at")
    op.execute("ALTER TABLE signal_deliveries DROP COLUMN IF EXISTS dispatch_started_at")
    op.execute("ALTER TABLE signal_deliveries DROP COLUMN IF EXISTS delivery_state")
