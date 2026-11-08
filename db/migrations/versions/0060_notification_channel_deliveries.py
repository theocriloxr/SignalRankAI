"""One row per notification and external channel (email, push) (8 Nov 2026).

Owner request: signals and updates by email and as app notifications on
desktops and phones, limited per tier like Telegram. ``notification_events``
already holds every user's signal and lifecycle notifications; the dispatcher
claims (notification, channel) here before sending, so each is sent at most
once across restarts and workers. New table only; no existing data changes.

Revision ID: 0060_notification_channels
Revises: 0059_close_pending_terminal
"""
from alembic import op

revision = "0060_notification_channels"
down_revision = "0059_close_pending_terminal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS notification_channel_deliveries (
            notification_id VARCHAR(36) NOT NULL REFERENCES notification_events(notification_id) ON DELETE CASCADE,
            channel VARCHAR(16) NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status VARCHAR(24) NOT NULL DEFAULT 'claimed',
            detail VARCHAR(240),
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            sent_at TIMESTAMP WITHOUT TIME ZONE,
            PRIMARY KEY (notification_id, channel)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notification_channel_deliveries_user_time "
        "ON notification_channel_deliveries(user_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notification_channel_deliveries")
