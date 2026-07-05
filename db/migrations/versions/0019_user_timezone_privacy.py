"""Privacy-safe user timezone preferences and travel mode.

Revision ID: 0019_user_timezone_privacy
Revises: 0018_signal_lifecycle_events
Create Date: 2026-07-05
"""

from alembic import op


revision = "0019_user_timezone_privacy"
down_revision = "0018_signal_lifecycle_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone_source VARCHAR(24)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone_updated_at TIMESTAMP")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone_auto_update BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_location_lat FLOAT")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_location_lon FLOAT")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_location_accuracy_m FLOAT")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_location_at TIMESTAMP")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS locale VARCHAR(16)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS time_format VARCHAR(8) NOT NULL DEFAULT '12h'")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS time_format")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS locale")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS last_location_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS last_location_accuracy_m")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS last_location_lon")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS last_location_lat")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS timezone_auto_update")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS timezone_updated_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS timezone_source")
