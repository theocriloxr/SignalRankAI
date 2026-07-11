"""Persist complete signal lifecycle and event notification state.

Revision ID: 0018_signal_lifecycle_events
Revises: 0017_signal_delivery_proof
Create Date: 2026-07-05
"""

from alembic import op


revision = "0018_signal_lifecycle_events"
down_revision = "0017_signal_delivery_proof"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS generated_at_utc TIMESTAMP")
    op.execute("ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS delivered_at_utc TIMESTAMP")
    op.execute("ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS display_timezone VARCHAR(64)")
    op.execute("ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS display_generated_at VARCHAR(64)")
    op.execute("ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS display_delivered_at VARCHAR(64)")
    op.execute("ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS delivery_latency_seconds INTEGER")
    op.execute("ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS signal_age_at_delivery_seconds INTEGER")
    op.execute("""
        CREATE TABLE IF NOT EXISTS signal_lifecycles (
            signal_id VARCHAR(36) PRIMARY KEY REFERENCES signals(signal_id),
            state VARCHAR(32) NOT NULL DEFAULT 'WATCHING_FOR_ENTRY',
            generated_at TIMESTAMP, watch_started_at TIMESTAMP NOT NULL DEFAULT NOW(),
            entry_touched_at TIMESTAMP, tp1_hit_at TIMESTAMP, tp2_hit_at TIMESTAMP,
            tp3_hit_at TIMESTAMP, sl_hit_at TIMESTAMP, breakeven_at TIMESTAMP,
            expired_at TIMESTAMP, closed_at TIMESTAMP, last_price FLOAT,
            last_checked_at TIMESTAMP, max_price_seen FLOAT, min_price_seen FLOAT,
            mfe_pct FLOAT NOT NULL DEFAULT 0, mae_pct FLOAT NOT NULL DEFAULT 0,
            mfe_r FLOAT NOT NULL DEFAULT 0, mae_r FLOAT NOT NULL DEFAULT 0,
            entry_latency_seconds INTEGER, time_to_tp1_seconds INTEGER,
            time_to_tp2_seconds INTEGER, time_to_tp3_seconds INTEGER,
            time_to_sl_seconds INTEGER, tp1_before_sl BOOLEAN NOT NULL DEFAULT FALSE,
            tp2_before_sl BOOLEAN NOT NULL DEFAULT FALSE,
            tp3_before_sl BOOLEAN NOT NULL DEFAULT FALSE,
            reversed_after_tp1 BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_signal_lifecycles_state ON signal_lifecycles(state)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS signal_tracking_events (
            id BIGSERIAL PRIMARY KEY, signal_id VARCHAR(36) NOT NULL REFERENCES signals(signal_id),
            event_type VARCHAR(32) NOT NULL, event_time TIMESTAMP NOT NULL DEFAULT NOW(),
            price FLOAT, r_multiple FLOAT, meta JSON NOT NULL DEFAULT '{}'::json,
            notified_at TIMESTAMP,
            CONSTRAINT uq_signal_tracking_event_stage UNIQUE(signal_id, event_type)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_signal_tracking_events_signal ON signal_tracking_events(signal_id)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS signal_event_notifications (
            id BIGSERIAL PRIMARY KEY, event_id BIGINT NOT NULL REFERENCES signal_tracking_events(id),
            signal_id VARCHAR(36) NOT NULL REFERENCES signals(signal_id), event_type VARCHAR(32) NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(id), telegram_user_id BIGINT NOT NULL,
            delivery_id INTEGER REFERENCES signal_deliveries(id), chat_id BIGINT,
            source_message_id BIGINT, sent_message_id BIGINT,
            delivery_state VARCHAR(16) NOT NULL DEFAULT 'pending',
            sent_ok BOOLEAN NOT NULL DEFAULT FALSE, error TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(), sent_at TIMESTAMP,
            CONSTRAINT uq_signal_event_notification_recipient UNIQUE(signal_id, event_type, user_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_signal_event_notifications_state ON signal_event_notifications(delivery_state)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS signal_event_notifications")
    op.execute("DROP TABLE IF EXISTS signal_tracking_events")
    op.execute("DROP TABLE IF EXISTS signal_lifecycles")
    op.execute("ALTER TABLE signal_deliveries DROP COLUMN IF EXISTS signal_age_at_delivery_seconds")
    op.execute("ALTER TABLE signal_deliveries DROP COLUMN IF EXISTS delivery_latency_seconds")
    op.execute("ALTER TABLE signal_deliveries DROP COLUMN IF EXISTS display_delivered_at")
    op.execute("ALTER TABLE signal_deliveries DROP COLUMN IF EXISTS display_generated_at")
    op.execute("ALTER TABLE signal_deliveries DROP COLUMN IF EXISTS display_timezone")
    op.execute("ALTER TABLE signal_deliveries DROP COLUMN IF EXISTS delivered_at_utc")
    op.execute("ALTER TABLE signal_deliveries DROP COLUMN IF EXISTS generated_at_utc")
