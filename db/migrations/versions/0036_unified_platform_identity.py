"""Unified web/mobile/Telegram identity and product surface.

Revision ID: 0036_unified_platform_identity
Revises: 0035_staging_certification_ecosystem
Create Date: 2026-08-06

This migration keeps the existing ``users.id`` as the canonical user key so all
legacy Telegram signals, subscriptions, deliveries and paper-trading records
retain their relationships.  ``telegram_user_id`` becomes optional, allowing a
user to register in the app first and link Telegram later.
"""
from alembic import op

revision = "0036_unified_platform_identity"
down_revision = "0035_staging_certification_ecosystem"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Canonical user profile. Existing Telegram users remain in-place.
    op.execute("ALTER TABLE users ALTER COLUMN telegram_user_id DROP NOT NULL")
    for statement in (
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS public_user_id VARCHAR(36)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS primary_email VARCHAR(320)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS primary_phone VARCHAR(32)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name VARCHAR(160)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS country VARCHAR(2)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_currency VARCHAR(8) NOT NULL DEFAULT 'USD'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS account_status VARCHAR(24) NOT NULL DEFAULT 'active'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_status VARCHAR(32) NOT NULL DEFAULT 'pending'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMP WITHOUT TIME ZONE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()",
    ):
        op.execute(statement)
    op.execute(
        "UPDATE users SET public_user_id = gen_random_uuid()::text "
        "WHERE public_user_id IS NULL OR public_user_id = ''"
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_public_user_id ON users(public_user_id)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_primary_email_ci "
        "ON users(LOWER(primary_email)) WHERE primary_email IS NOT NULL"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS auth_identities (
            identity_id VARCHAR(36) PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider VARCHAR(32) NOT NULL,
            provider_subject_id VARCHAR(320) NOT NULL,
            verified BOOLEAN NOT NULL DEFAULT FALSE,
            verified_at TIMESTAMP WITHOUT TIME ZONE,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            last_used_at TIMESTAMP WITHOUT TIME ZONE,
            disabled_at TIMESTAMP WITHOUT TIME ZONE,
            CONSTRAINT uq_auth_identity_provider_subject UNIQUE(provider, provider_subject_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_auth_identities_user ON auth_identities(user_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS password_credentials (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            password_hash TEXT NOT NULL,
            password_version INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            changed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            compromised_at TIMESTAMP WITHOUT TIME ZONE
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_sessions (
            session_id VARCHAR(36) PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            refresh_token_hash VARCHAR(64) NOT NULL UNIQUE,
            session_family_id VARCHAR(36) NOT NULL,
            device_id VARCHAR(36),
            user_agent_hash VARCHAR(64),
            ip_hash VARCHAR(64),
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            last_used_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            revoked_at TIMESTAMP WITHOUT TIME ZONE,
            revoke_reason VARCHAR(128),
            rotated_to_session_id VARCHAR(36),
            refresh_reuse_detected BOOLEAN NOT NULL DEFAULT FALSE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_sessions_user_active ON user_sessions(user_id, revoked_at, expires_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_sessions_family ON user_sessions(session_family_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS login_challenges (
            challenge_id VARCHAR(36) PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            purpose VARCHAR(48) NOT NULL,
            token_hash VARCHAR(64) UNIQUE,
            code_hash VARCHAR(64),
            environment VARCHAR(24) NOT NULL DEFAULT 'production',
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 5,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            consumed_at TIMESTAMP WITHOUT TIME ZONE,
            consumed_ip_hash VARCHAR(64)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_login_challenges_code ON login_challenges(code_hash, purpose, expires_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_login_challenges_user ON login_challenges(user_id, purpose, expires_at)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_devices (
            device_id VARCHAR(36) PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            device_name VARCHAR(160),
            platform VARCHAR(32),
            app_version VARCHAR(32),
            trusted BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            last_active_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            revoked_at TIMESTAMP WITHOUT TIME ZONE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_devices_user ON user_devices(user_id, revoked_at)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS security_events (
            event_id BIGSERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            event_type VARCHAR(64) NOT NULL,
            severity VARCHAR(16) NOT NULL DEFAULT 'info',
            request_id VARCHAR(64),
            session_id VARCHAR(36),
            device_id VARCHAR(36),
            ip_hash VARCHAR(64),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_security_events_user_time ON security_events(user_id, created_at DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS account_link_requests (
            link_id VARCHAR(36) PRIMARY KEY,
            requesting_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider VARCHAR(32) NOT NULL,
            provider_subject_id VARCHAR(320),
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            status VARCHAR(24) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            completed_at TIMESTAMP WITHOUT TIME ZONE,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS account_merge_records (
            merge_id VARCHAR(36) PRIMARY KEY,
            canonical_user_id INTEGER NOT NULL REFERENCES users(id),
            merged_user_id INTEGER NOT NULL REFERENCES users(id),
            status VARCHAR(24) NOT NULL DEFAULT 'completed',
            evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            created_by INTEGER REFERENCES users(id),
            CONSTRAINT uq_merged_user_once UNIQUE(merged_user_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS watchlists (
            watchlist_id VARCHAR(36) PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_watchlist_user_name UNIQUE(user_id, name)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS watchlist_items (
            watchlist_id VARCHAR(36) NOT NULL REFERENCES watchlists(watchlist_id) ON DELETE CASCADE,
            instrument_id VARCHAR(128) NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            PRIMARY KEY(watchlist_id, instrument_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS notification_preferences (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            telegram_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            web_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            email_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            push_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            webhook_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            quiet_hours_start VARCHAR(5),
            quiet_hours_end VARCHAR(5),
            timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
            preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS push_devices (
            push_device_id VARCHAR(36) PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            device_id VARCHAR(36),
            provider VARCHAR(24) NOT NULL DEFAULT 'expo',
            push_token_hash VARCHAR(64) NOT NULL UNIQUE,
            encrypted_push_token TEXT NOT NULL,
            platform VARCHAR(24),
            app_version VARCHAR(32),
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            last_registered_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            revoked_at TIMESTAMP WITHOUT TIME ZONE
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS organizations (
            organization_id VARCHAR(36) PRIMARY KEY,
            name VARCHAR(180) NOT NULL,
            slug VARCHAR(100) NOT NULL UNIQUE,
            owner_user_id INTEGER NOT NULL REFERENCES users(id),
            tier VARCHAR(24) NOT NULL DEFAULT 'professional',
            status VARCHAR(24) NOT NULL DEFAULT 'active',
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS organization_members (
            organization_id VARCHAR(36) NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role VARCHAR(32) NOT NULL DEFAULT 'viewer',
            status VARCHAR(24) NOT NULL DEFAULT 'active',
            joined_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            PRIMARY KEY(organization_id, user_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_organization_members_user ON organization_members(user_id, status)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS webhook_endpoints (
            webhook_endpoint_id VARCHAR(36) PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            organization_id VARCHAR(36) REFERENCES organizations(organization_id) ON DELETE CASCADE,
            url TEXT NOT NULL,
            secret_hash VARCHAR(64) NOT NULL,
            encrypted_secret TEXT NOT NULL,
            subscribed_events JSONB NOT NULL DEFAULT '[]'::jsonb,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_webhook_owner CHECK (user_id IS NOT NULL OR organization_id IS NOT NULL)
        )
    """)

    # Backfill Telegram identities without changing existing record ownership.
    op.execute("""
        INSERT INTO auth_identities(
            identity_id, user_id, provider, provider_subject_id,
            verified, verified_at, metadata, created_at
        )
        SELECT gen_random_uuid()::text, id, 'telegram', telegram_user_id::text,
               TRUE, COALESCE(created_at, NOW()),
               jsonb_build_object('legacy_username', username),
               COALESCE(created_at, NOW())
        FROM users
        WHERE telegram_user_id IS NOT NULL
        ON CONFLICT(provider, provider_subject_id) DO NOTHING
    """)
    op.execute("""
        INSERT INTO notification_preferences(user_id, telegram_enabled, timezone)
        SELECT id, CASE WHEN telegram_user_id IS NULL THEN FALSE ELSE TRUE END,
               COALESCE(timezone, 'UTC')
        FROM users
        ON CONFLICT(user_id) DO NOTHING
    """)


def downgrade() -> None:
    # Identity history is deliberately retained on downgrade. Dropping the
    # tables would orphan application users and destroy audit evidence.
    pass
