"""Platform hardening: webhook idempotency, api tokens, indexes, vip webhooks, shadow predictions

Revision ID: 0011_platform_hardening_security_scaling
Revises: 0010_consolidate_full_schema
Create Date: 2026-04-05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0011_platform_hardening_security_scaling"
down_revision = "0010_consolidate_full_schema"
branch_labels = None
depends_on = None


def _exec(sql: str) -> None:
    op.execute(sa.text(sql))


def upgrade() -> None:
    _exec(
        """
        CREATE TABLE IF NOT EXISTS processed_webhook_events (
            id SERIAL PRIMARY KEY,
            event_id VARCHAR(128) NOT NULL,
            provider VARCHAR(32) NOT NULL DEFAULT 'paystack',
            event_type VARCHAR(64) NOT NULL,
            reference VARCHAR(128),
            payload_hash VARCHAR(128) NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            meta JSONB NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT uq_processed_webhook_events_event_id UNIQUE (event_id)
        )
        """
    )
    _exec("CREATE INDEX IF NOT EXISTS ix_processed_webhook_events_event_id ON processed_webhook_events (event_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_processed_webhook_events_reference ON processed_webhook_events (reference)")
    _exec("CREATE INDEX IF NOT EXISTS ix_processed_webhook_events_event_type ON processed_webhook_events (event_type)")

    _exec(
        """
        CREATE TABLE IF NOT EXISTS api_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            token_hash VARCHAR(128) NOT NULL,
            token_prefix VARCHAR(16) NOT NULL,
            scope VARCHAR(32) NOT NULL DEFAULT 'signals:read',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMP,
            revoked_at TIMESTAMP,
            last_used_at TIMESTAMP,
            CONSTRAINT uq_api_tokens_token_hash UNIQUE (token_hash)
        )
        """
    )
    _exec("CREATE INDEX IF NOT EXISTS ix_api_tokens_user_id ON api_tokens (user_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_api_tokens_token_hash ON api_tokens (token_hash)")
    _exec("CREATE INDEX IF NOT EXISTS ix_api_tokens_scope ON api_tokens (scope)")
    _exec("CREATE INDEX IF NOT EXISTS ix_api_tokens_expires_at ON api_tokens (expires_at)")
    _exec("CREATE INDEX IF NOT EXISTS ix_api_tokens_revoked_at ON api_tokens (revoked_at)")

    _exec(
        """
        CREATE TABLE IF NOT EXISTS user_webhooks (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
            webhook_url TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            secret_token VARCHAR(128),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    _exec("CREATE INDEX IF NOT EXISTS ix_user_webhooks_user_id ON user_webhooks (user_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_user_webhooks_is_active ON user_webhooks (is_active)")

    _exec(
        """
        CREATE TABLE IF NOT EXISTS ml_shadow_predictions (
            id SERIAL PRIMARY KEY,
            signal_id VARCHAR(36),
            model_name VARCHAR(128) NOT NULL,
            model_version VARCHAR(64),
            probability FLOAT NOT NULL,
            is_shadow BOOLEAN NOT NULL DEFAULT TRUE,
            feature_schema_ok BOOLEAN NOT NULL DEFAULT TRUE,
            meta JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    _exec("CREATE INDEX IF NOT EXISTS ix_ml_shadow_predictions_signal_id ON ml_shadow_predictions (signal_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_ml_shadow_predictions_model_name ON ml_shadow_predictions (model_name)")
    _exec("CREATE INDEX IF NOT EXISTS ix_ml_shadow_predictions_is_shadow ON ml_shadow_predictions (is_shadow)")

    # Critical query-path indexes
    _exec("CREATE INDEX IF NOT EXISTS ix_subscriptions_user_status_exp ON subscriptions (user_id, status, expires_at DESC)")
    _exec("CREATE INDEX IF NOT EXISTS ix_signals_created_archived_expired ON signals (created_at DESC, archived, expired)")
    _exec("CREATE INDEX IF NOT EXISTS ix_signals_asset_tf_created ON signals (asset, timeframe, created_at DESC)")
    _exec("CREATE INDEX IF NOT EXISTS ix_decision_log_created_decision_asset_tf ON decision_log (created_at DESC, decision, asset, timeframe)")
    _exec("CREATE INDEX IF NOT EXISTS ix_outcomes_signal_closed ON outcomes (signal_id, closed_at DESC)")
    _exec("CREATE INDEX IF NOT EXISTS ix_payment_events_created_kind_tier ON payment_events (created_at DESC, kind, tier)")
    _exec("CREATE INDEX IF NOT EXISTS ix_free_signal_queue_status_deliver_after ON free_signal_queue (status, deliver_after)")


def downgrade() -> None:
    _exec("DROP INDEX IF EXISTS ix_free_signal_queue_status_deliver_after")
    _exec("DROP INDEX IF EXISTS ix_payment_events_created_kind_tier")
    _exec("DROP INDEX IF EXISTS ix_outcomes_signal_closed")
    _exec("DROP INDEX IF EXISTS ix_decision_log_created_decision_asset_tf")
    _exec("DROP INDEX IF EXISTS ix_signals_asset_tf_created")
    _exec("DROP INDEX IF EXISTS ix_signals_created_archived_expired")
    _exec("DROP INDEX IF EXISTS ix_subscriptions_user_status_exp")

    _exec("DROP TABLE IF EXISTS ml_shadow_predictions")
    _exec("DROP TABLE IF EXISTS user_webhooks")
    _exec("DROP TABLE IF EXISTS api_tokens")
    _exec("DROP TABLE IF EXISTS processed_webhook_events")
