"""Consolidate full schema — catch-up migration.

This migration is the single authoritative "catch-up" step between the old
db/migrations chain (which ended at 0009_archived_column) and the full set of
models in db/models.py.

All DDL uses IF NOT EXISTS / ADD COLUMN IF NOT EXISTS so it is safe to run
against any database state — fresh, partially migrated, or fully bootstrapped
by the auto_ops failsafe.

Revision ID: 0010_consolidate_full_schema
Revises: 0009_archived_column
Create Date: 2026-03-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_consolidate_full_schema"
down_revision = "0009_archived_column"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _exec(sql: str) -> None:
    op.execute(sa.text(sql))


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:

    # ── 1. users — additional columns ────────────────────────────────────────
    _exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT")
    _exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS fixed_lot_size FLOAT NOT NULL DEFAULT 0.01")
    _exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_executions_today INTEGER NOT NULL DEFAULT 0")
    _exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_executions_reset_at TIMESTAMP")
    _exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS max_risk_percentage FLOAT NOT NULL DEFAULT 1.0")
    _exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS paystack_subscription_code VARCHAR(128)")
    _exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS paystack_customer_code VARCHAR(128)")
    _exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_renew BOOLEAN NOT NULL DEFAULT TRUE")
    _exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_count INTEGER DEFAULT 0")
    _exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS premium_until TIMESTAMP")
    _exec("CREATE INDEX IF NOT EXISTS ix_users_referred_by ON users (referred_by)")
    _exec("CREATE INDEX IF NOT EXISTS ix_users_paystack_subscription_code ON users (paystack_subscription_code)")

    # ── 2. subscriptions — bonus_days ─────────────────────────────────────────
    _exec("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS bonus_days INTEGER NOT NULL DEFAULT 0")

    # ── 3. signals — additional columns ──────────────────────────────────────
    _exec("ALTER TABLE signals ADD COLUMN IF NOT EXISTS ml_probability FLOAT")
    _exec("ALTER TABLE signals ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP")
    _exec("ALTER TABLE signals ADD COLUMN IF NOT EXISTS expired BOOLEAN NOT NULL DEFAULT FALSE")
    _exec("ALTER TABLE signals ADD COLUMN IF NOT EXISTS is_near_order_block BOOLEAN NOT NULL DEFAULT FALSE")
    _exec("CREATE INDEX IF NOT EXISTS ix_signals_expires_at ON signals (expires_at)")
    _exec("CREATE INDEX IF NOT EXISTS ix_signals_expired ON signals (expired)")

    # ── 4. referrals — additional columns ────────────────────────────────────
    _exec("ALTER TABLE referrals ADD COLUMN IF NOT EXISTS is_successful BOOLEAN NOT NULL DEFAULT FALSE")
    _exec("ALTER TABLE referrals ADD COLUMN IF NOT EXISTS reward_applied BOOLEAN NOT NULL DEFAULT FALSE")
    _exec("ALTER TABLE referrals ADD COLUMN IF NOT EXISTS successful_at TIMESTAMP")
    _exec("ALTER TABLE referrals ADD COLUMN IF NOT EXISTS referrer_notified_at TIMESTAMP")

    # ── 5. trades ─────────────────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS trades (
            trade_id          VARCHAR(36)   PRIMARY KEY,
            signal_id         VARCHAR(36)   REFERENCES signals(signal_id),
            symbol            VARCHAR(32)   NOT NULL,
            direction         VARCHAR(8)    NOT NULL,
            entry_price       FLOAT         NOT NULL,
            entry_time        TIMESTAMP     NOT NULL DEFAULT NOW(),
            position_size     FLOAT         NOT NULL,
            stop_loss         FLOAT         NOT NULL,
            take_profit       TEXT          NOT NULL,
            status            VARCHAR(16)   NOT NULL DEFAULT 'open',
            exit_price        FLOAT,
            exit_time         TIMESTAMP,
            exit_reason       VARCHAR(64),
            pnl               FLOAT,
            pnl_pct           FLOAT,
            max_drawdown      FLOAT,
            max_profit        FLOAT,
            partial_exits     JSONB         NOT NULL DEFAULT '{}'::jsonb,
            max_risk_pct      FLOAT         NOT NULL DEFAULT 5.0,
            atr               FLOAT,
            trade_metadata    JSONB         NOT NULL DEFAULT '{}'::jsonb,
            created_at        TIMESTAMP     NOT NULL DEFAULT NOW(),
            updated_at        TIMESTAMP     NOT NULL DEFAULT NOW()
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS ix_trades_signal_id   ON trades (signal_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_trades_symbol      ON trades (symbol)")
    _exec("CREATE INDEX IF NOT EXISTS ix_trades_status      ON trades (status)")

    # ── 6. signal_deliveries ─────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS signal_deliveries (
            id            SERIAL        PRIMARY KEY,
            user_id       INTEGER       NOT NULL REFERENCES users(id),
            signal_id     VARCHAR(36)   NOT NULL REFERENCES signals(signal_id),
            tier_at_send  VARCHAR(16)   NOT NULL DEFAULT 'free',
            delivered_at  TIMESTAMP     NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_signal_delivery_user_signal UNIQUE (user_id, signal_id)
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS ix_signal_deliveries_user_id   ON signal_deliveries (user_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_signal_deliveries_signal_id ON signal_deliveries (signal_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_signal_deliveries_tier_at_send ON signal_deliveries (tier_at_send)")

    # ── 7. free_signal_queue ─────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS free_signal_queue (
            id            SERIAL       PRIMARY KEY,
            user_id       INTEGER      NOT NULL REFERENCES users(id),
            date          TIMESTAMP    NOT NULL,
            signal_id     VARCHAR(36)  NOT NULL REFERENCES signals(signal_id),
            asset         VARCHAR(32)  NOT NULL,
            timeframe     VARCHAR(8)   NOT NULL,
            direction     VARCHAR(8)   NOT NULL,
            score         INTEGER      NOT NULL DEFAULT 0,
            queued_at     TIMESTAMP    NOT NULL DEFAULT NOW(),
            deliver_after TIMESTAMP    NOT NULL,
            sent_at       TIMESTAMP,
            status        VARCHAR(16)  NOT NULL DEFAULT 'queued'
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS ix_free_signal_queue_user_id      ON free_signal_queue (user_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_free_signal_queue_signal_id    ON free_signal_queue (signal_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_free_signal_queue_date         ON free_signal_queue (date)")
    _exec("CREATE INDEX IF NOT EXISTS ix_free_signal_queue_deliver_after ON free_signal_queue (deliver_after)")
    _exec("CREATE INDEX IF NOT EXISTS ix_free_signal_queue_status       ON free_signal_queue (status)")

    # ── 8. signal_corrections ────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS signal_corrections (
            id                    SERIAL        PRIMARY KEY,
            original_signal_id    VARCHAR(36)   NOT NULL REFERENCES signals(signal_id),
            corrected_signal_id   VARCHAR(36)   REFERENCES signals(signal_id),
            error_type            VARCHAR(64)   NOT NULL,
            error_description     TEXT          NOT NULL,
            users_notified        INTEGER       NOT NULL DEFAULT 0,
            correction_sent_at    TIMESTAMP,
            created_at            TIMESTAMP     NOT NULL DEFAULT NOW(),
            meta                  JSONB         NOT NULL DEFAULT '{}'::jsonb
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS ix_signal_corrections_original_signal_id  ON signal_corrections (original_signal_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_signal_corrections_corrected_signal_id ON signal_corrections (corrected_signal_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_signal_corrections_error_type          ON signal_corrections (error_type)")

    # ── 9. signal_engagements ────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS signal_engagements (
            id         SERIAL       PRIMARY KEY,
            user_id    INTEGER      NOT NULL REFERENCES users(id),
            signal_id  VARCHAR(36)  NOT NULL REFERENCES signals(signal_id),
            reaction   VARCHAR(16)  NOT NULL,
            created_at TIMESTAMP    NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_signal_engagement_user_signal UNIQUE (user_id, signal_id)
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS ix_signal_engagements_user_id   ON signal_engagements (user_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_signal_engagements_signal_id ON signal_engagements (signal_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_signal_engagements_reaction  ON signal_engagements (reaction)")

    # ── 10. active_signal_messages ───────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS active_signal_messages (
            id         SERIAL       PRIMARY KEY,
            user_id    INTEGER      NOT NULL REFERENCES users(id),
            signal_id  VARCHAR(36)  NOT NULL REFERENCES signals(signal_id),
            chat_id    BIGINT       NOT NULL,
            message_id BIGINT       NOT NULL,
            is_active  BOOLEAN      NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP    NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_active_signal_msg_user_signal UNIQUE (user_id, signal_id)
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS ix_active_signal_messages_user_id   ON active_signal_messages (user_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_active_signal_messages_signal_id ON active_signal_messages (signal_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_active_signal_messages_is_active ON active_signal_messages (is_active)")

    # ── 11. economic_events ──────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS economic_events (
            id          SERIAL        PRIMARY KEY,
            event_date  TIMESTAMP     NOT NULL,
            currency    VARCHAR(8)    NOT NULL,
            title       VARCHAR(256)  NOT NULL,
            impact      VARCHAR(8)    NOT NULL DEFAULT 'low',
            source      VARCHAR(64),
            fetched_at  TIMESTAMP     NOT NULL DEFAULT NOW()
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS ix_economic_events_event_date ON economic_events (event_date)")
    _exec("CREATE INDEX IF NOT EXISTS ix_economic_events_currency   ON economic_events (currency)")
    _exec("CREATE INDEX IF NOT EXISTS ix_economic_events_impact     ON economic_events (impact)")

    # ── 12. mt5_executions ───────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS mt5_executions (
            id                   SERIAL        PRIMARY KEY,
            user_id              INTEGER       NOT NULL REFERENCES users(id),
            signal_id            VARCHAR(36)   REFERENCES signals(signal_id),
            metaapi_account_id   VARCHAR(128)  NOT NULL,
            order_id             VARCHAR(128),
            symbol               VARCHAR(32)   NOT NULL,
            direction            VARCHAR(8)    NOT NULL,
            lot_size             FLOAT         NOT NULL,
            entry_price          FLOAT         NOT NULL,
            stop_loss            FLOAT         NOT NULL,
            take_profit          TEXT          NOT NULL,
            status               VARCHAR(16)   NOT NULL DEFAULT 'pending',
            tier_at_execution    VARCHAR(16)   NOT NULL DEFAULT 'premium',
            realized_pnl         FLOAT,
            realized_pnl_pct     FLOAT,
            executed_at          TIMESTAMP     NOT NULL DEFAULT NOW(),
            closed_at            TIMESTAMP,
            meta                 JSONB         NOT NULL DEFAULT '{}'::jsonb
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS ix_mt5_executions_user_id   ON mt5_executions (user_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_mt5_executions_signal_id ON mt5_executions (signal_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_mt5_executions_status    ON mt5_executions (status)")

    # ── 13. vip_waitlist ─────────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS vip_waitlist (
            id                SERIAL     PRIMARY KEY,
            user_id           INTEGER    NOT NULL UNIQUE REFERENCES users(id),
            joined_at         TIMESTAMP  NOT NULL DEFAULT NOW(),
            notified_at       TIMESTAMP,
            invited_at        TIMESTAMP,
            invite_expires_at TIMESTAMP
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS ix_vip_waitlist_user_id           ON vip_waitlist (user_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_vip_waitlist_invite_expires_at ON vip_waitlist (invite_expires_at)")

    # ── 14. mt5_credentials ──────────────────────────────────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS mt5_credentials (
            id                    SERIAL        PRIMARY KEY,
            user_id               INTEGER       NOT NULL UNIQUE REFERENCES users(id),
            mt5_login             VARCHAR(64)   NOT NULL,
            password_encrypted    VARCHAR(512)  NOT NULL,
            server                VARCHAR(128)  NOT NULL,
            metaapi_account_id    VARCHAR(128),
            created_at            TIMESTAMP     NOT NULL DEFAULT NOW(),
            updated_at            TIMESTAMP     NOT NULL DEFAULT NOW()
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS ix_mt5_credentials_user_id ON mt5_credentials (user_id)")

    # ── 15. decision_log (already in auto_ops failsafe but ensure here too) ──
    _exec("""
        CREATE TABLE IF NOT EXISTS decision_log (
            id          SERIAL        PRIMARY KEY,
            signal_id   VARCHAR(36),
            asset       VARCHAR(32),
            timeframe   VARCHAR(8),
            decision    VARCHAR(32)   NOT NULL,
            reason      TEXT,
            meta        JSONB         NOT NULL DEFAULT '{}'::jsonb,
            created_at  TIMESTAMP     NOT NULL DEFAULT NOW()
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS ix_decision_log_signal_id  ON decision_log (signal_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_decision_log_asset      ON decision_log (asset)")
    _exec("CREATE INDEX IF NOT EXISTS ix_decision_log_decision   ON decision_log (decision)")
    _exec("CREATE INDEX IF NOT EXISTS ix_decision_log_created_at ON decision_log (created_at)")

    # ── 16. ml_rejected_signals (already in auto_ops failsafe) ───────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS ml_rejected_signals (
            id                  SERIAL        PRIMARY KEY,
            asset               VARCHAR(32)   NOT NULL,
            timeframe           VARCHAR(8)    NOT NULL,
            direction           VARCHAR(8)    NOT NULL,
            entry               FLOAT         NOT NULL,
            stop_loss           FLOAT         NOT NULL,
            take_profit         TEXT          NOT NULL,
            ml_probability      FLOAT         NOT NULL,
            rejection_reason    VARCHAR(128)  NOT NULL,
            features            JSONB         NOT NULL DEFAULT '{}'::jsonb,
            actual_outcome      VARCHAR(32),
            outcome_tracked_at  TIMESTAMP,
            created_at          TIMESTAMP     NOT NULL DEFAULT NOW()
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS ix_ml_rejected_signals_asset           ON ml_rejected_signals (asset)")
    _exec("CREATE INDEX IF NOT EXISTS ix_ml_rejected_signals_timeframe       ON ml_rejected_signals (timeframe)")
    _exec("CREATE INDEX IF NOT EXISTS ix_ml_rejected_signals_actual_outcome  ON ml_rejected_signals (actual_outcome)")

    # ── 17. managed_assets (already in auto_ops failsafe) ────────────────────
    _exec("""
        CREATE TABLE IF NOT EXISTS managed_assets (
            id               SERIAL        PRIMARY KEY,
            symbol           VARCHAR(32)   NOT NULL,
            asset_type       VARCHAR(16)   NOT NULL DEFAULT 'crypto',
            is_active        BOOLEAN       NOT NULL DEFAULT TRUE,
            added_by         BIGINT,
            note             VARCHAR(256),
            last_analyzed_at TIMESTAMP,
            created_at       TIMESTAMP     NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMP     NOT NULL DEFAULT NOW()
        )
    """)
    _exec("CREATE UNIQUE INDEX IF NOT EXISTS ix_managed_assets_symbol       ON managed_assets (symbol)")
    _exec("CREATE INDEX IF NOT EXISTS ix_managed_assets_is_active           ON managed_assets (is_active)")
    _exec("CREATE INDEX IF NOT EXISTS ix_managed_assets_last_analyzed       ON managed_assets (last_analyzed_at ASC NULLS FIRST)")
    # Belt-and-suspenders for existing tables created before last_analyzed_at column existed
    _exec("ALTER TABLE managed_assets ADD COLUMN IF NOT EXISTS last_analyzed_at TIMESTAMP")


# ---------------------------------------------------------------------------
# downgrade — intentionally no-op: column/table drops are destructive and
# we never roll back a consolidation migration in production.
# ---------------------------------------------------------------------------

def downgrade() -> None:
    pass
