"""Bridge legacy runtime schema repairs into the canonical Alembic chain.

Revision ID: 0048_runtime_schema_bridge
Revises: 0047_event_outbox
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0048_runtime_schema_bridge"
down_revision = "0047_event_outbox"
branch_labels = None
depends_on = None


def _exec(sql: str) -> None:
    op.execute(sa.text(sql))


def upgrade() -> None:
    # Fresh databases use db/migrations as the canonical chain. Historically,
    # several columns lived only in the retired parallel alembic/migrations
    # tree or startup auto-repair. Move those guarantees into Alembic so a
    # clean database at head is sufficient for runtime boot/replay.
    user_columns = (
        "premium_until TIMESTAMP",
        "referred_by BIGINT",
        "fixed_lot_size FLOAT NOT NULL DEFAULT 0.01",
        "daily_executions_today INTEGER NOT NULL DEFAULT 0",
        "daily_executions_reset_at TIMESTAMP",
        "max_risk_percentage FLOAT NOT NULL DEFAULT 1.0",
        "max_daily_drawdown_pct FLOAT NOT NULL DEFAULT 8.0",
        "execution_mode VARCHAR(16) NOT NULL DEFAULT 'manual'",
        "auto_signals_daily_limit INTEGER NOT NULL DEFAULT 3",
        "paystack_subscription_code VARCHAR(128)",
        "paystack_customer_code VARCHAR(128)",
        "auto_renew BOOLEAN NOT NULL DEFAULT TRUE",
        "referral_count INTEGER DEFAULT 0",
        "accepted_terms BOOLEAN NOT NULL DEFAULT FALSE",
        "timezone VARCHAR(64)",
        "timezone_source VARCHAR(24)",
        "timezone_updated_at TIMESTAMP",
        "timezone_auto_update BOOLEAN NOT NULL DEFAULT FALSE",
        "last_location_lat FLOAT",
        "last_location_lon FLOAT",
        "last_location_accuracy_m FLOAT",
        "last_location_at TIMESTAMP",
        "locale VARCHAR(16)",
        "time_format VARCHAR(8) NOT NULL DEFAULT '12h'",
        "dca_profile VARCHAR(32)",
    )
    for definition in user_columns:
        _exec(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {definition}")

    signal_columns = (
        "status VARCHAR(16) NOT NULL DEFAULT 'issued'",
        "ml_probability FLOAT",
        "trade_profile VARCHAR(16)",
        "asset_class VARCHAR(16)",
        "target_model VARCHAR(32)",
        "expected_duration VARCHAR(64)",
        "expires_at TIMESTAMP",
        "expired BOOLEAN NOT NULL DEFAULT FALSE",
        "is_near_order_block BOOLEAN NOT NULL DEFAULT FALSE",
        "performance_version INTEGER NOT NULL DEFAULT 2",
    )
    for definition in signal_columns:
        _exec(f"ALTER TABLE signals ADD COLUMN IF NOT EXISTS {definition}")
    _exec("ALTER TABLE signals ALTER COLUMN performance_version SET DEFAULT 2")
    _exec("CREATE INDEX IF NOT EXISTS ix_signals_expires_at ON signals (expires_at)")
    _exec("CREATE INDEX IF NOT EXISTS ix_signals_expired ON signals (expired)")

    _exec("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS bonus_days INTEGER NOT NULL DEFAULT 0")

    referral_columns = (
        "is_successful BOOLEAN NOT NULL DEFAULT FALSE",
        "reward_applied BOOLEAN NOT NULL DEFAULT FALSE",
        "successful_at TIMESTAMP",
        "referrer_notified_at TIMESTAMP",
    )
    for definition in referral_columns:
        _exec(f"ALTER TABLE referrals ADD COLUMN IF NOT EXISTS {definition}")
    _exec("ALTER TABLE referral_rewards ADD COLUMN IF NOT EXISTS reference VARCHAR(128)")
    _exec("ALTER TABLE referral_rewards ADD COLUMN IF NOT EXISTS meta JSONB NOT NULL DEFAULT '{}'::jsonb")
    _exec(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_referral_rewards_reference "
        "ON referral_rewards(reference) WHERE reference IS NOT NULL"
    )

    outcome_columns = (
        "canonical_outcome VARCHAR(16)",
        "vip_fill_outcome VARCHAR(16)",
        "sentiment_outcome VARCHAR(16)",
    )
    for definition in outcome_columns:
        _exec(f"ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS {definition}")

    delivery_columns = (
        "sent_ok BOOLEAN NOT NULL DEFAULT FALSE",
        "delivery_state VARCHAR(16) NOT NULL DEFAULT 'reserved'",
        "attempt_count INTEGER NOT NULL DEFAULT 1",
        "dispatch_started_at TIMESTAMP",
        "telegram_send_started_at TIMESTAMP",
        "delivery_confirmed_at TIMESTAMP",
        "telegram_chat_id BIGINT",
        "telegram_message_id BIGINT",
        "telegram_api_result JSON DEFAULT '{}'::json",
        "generated_at_utc TIMESTAMP",
    )
    for definition in delivery_columns:
        _exec(f"ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS {definition}")

    # The canonical runtime model is the final arbiter for table existence.
    # create_all(checkfirst) creates only tables that are wholly absent; it does
    # not mutate existing tables and therefore complements the explicit bridge
    # columns above.
    bind = op.get_bind()
    from db.models import Base
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    # This bridge is deliberately non-destructive. Historical databases may
    # already have these columns from prior migrations or startup repairs.
    pass
