"""Complete account security, notifications and workspace collaboration.

Revision ID: 0038_account_security_product
Revises: 0037_unified_product_workspaces
"""
from __future__ import annotations

from alembic import op

revision = "0038_account_security_product"
down_revision = "0037_unified_product_workspaces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in (
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP WITHOUT TIME ZONE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS risk_profile JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS marketing_consent BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS privacy_consent_at TIMESTAMP WITHOUT TIME ZONE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_version VARCHAR(32)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_accepted_at TIMESTAMP WITHOUT TIME ZONE",
    ):
        op.execute(statement)

    op.execute("""
        CREATE TABLE IF NOT EXISTS email_outbox (
            email_id VARCHAR(36) PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            recipient VARCHAR(320) NOT NULL,
            template VARCHAR(64) NOT NULL,
            subject VARCHAR(240) NOT NULL,
            plain_body TEXT NOT NULL,
            html_body TEXT,
            context JSONB NOT NULL DEFAULT '{}'::jsonb,
            idempotency_key VARCHAR(160),
            status VARCHAR(24) NOT NULL DEFAULT 'pending',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            sent_at TIMESTAMP WITHOUT TIME ZONE,
            last_error VARCHAR(160),
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_email_outbox_idempotency ON email_outbox(idempotency_key) WHERE idempotency_key IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_outbox_pending ON email_outbox(status,next_attempt_at)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_mfa_totp (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            encrypted_secret TEXT NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT FALSE,
            verified_at TIMESTAMP WITHOUT TIME ZONE,
            last_used_step BIGINT,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS account_recovery_codes (
            recovery_code_id VARCHAR(36) PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code_hash VARCHAR(64) NOT NULL UNIQUE,
            used_at TIMESTAMP WITHOUT TIME ZONE,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_recovery_codes_user_unused ON account_recovery_codes(user_id,used_at)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS notification_events (
            notification_id VARCHAR(36) PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            event_type VARCHAR(96) NOT NULL,
            title VARCHAR(200) NOT NULL,
            body TEXT NOT NULL,
            severity VARCHAR(24) NOT NULL DEFAULT 'info',
            channel_data JSONB NOT NULL DEFAULT '{}'::jsonb,
            read_at TIMESTAMP WITHOUT TIME ZONE,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_notification_events_user_time ON notification_events(user_id,created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notification_events_unread ON notification_events(user_id,read_at) WHERE read_at IS NULL")

    op.execute("""
        CREATE TABLE IF NOT EXISTS organization_audit_events (
            audit_id VARCHAR(36) PRIMARY KEY,
            organization_id VARCHAR(36) NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
            actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            event_type VARCHAR(96) NOT NULL,
            target_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_org_audit_time ON organization_audit_events(organization_id,created_at DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_alerts (
            alert_id VARCHAR(36) PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            instrument_id VARCHAR(128),
            asset VARCHAR(32),
            alert_type VARCHAR(48) NOT NULL,
            condition JSONB NOT NULL DEFAULT '{}'::jsonb,
            channels JSONB NOT NULL DEFAULT '[\"telegram\",\"web\"]'::jsonb,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            last_triggered_at TIMESTAMP WITHOUT TIME ZONE,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_alerts_active ON user_alerts(user_id,active)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS app_feature_flags (
            flag_key VARCHAR(96) PRIMARY KEY,
            enabled BOOLEAN NOT NULL DEFAULT FALSE,
            environment VARCHAR(24) NOT NULL DEFAULT 'all',
            minimum_tier VARCHAR(24),
            configuration JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    # Account-security evidence and user-generated data are intentionally kept.
    pass
