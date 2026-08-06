"""Unified product workspaces, journal and professional API surfaces.

Revision ID: 0037_unified_product_workspaces
Revises: 0036_unified_platform_identity
"""
from __future__ import annotations

from alembic import op

revision = "0037_unified_product_workspaces"
down_revision = "0036_unified_platform_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS journal_entries (
            journal_entry_id VARCHAR(36) PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            signal_id VARCHAR(36),
            paper_position_id VARCHAR(36),
            title VARCHAR(180),
            notes TEXT NOT NULL DEFAULT '',
            emotion VARCHAR(64),
            mistake_category VARCHAR(96),
            plan_adherence SMALLINT,
            result_r DOUBLE PRECISION,
            tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            private BOOLEAN NOT NULL DEFAULT TRUE,
            occurred_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_journal_plan_adherence CHECK (plan_adherence IS NULL OR (plan_adherence >= 0 AND plan_adherence <= 100))
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_journal_entries_user_time ON journal_entries(user_id, occurred_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_journal_entries_signal ON journal_entries(signal_id) WHERE signal_id IS NOT NULL")

    op.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            key_id VARCHAR(36) PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            organization_id VARCHAR(36) REFERENCES organizations(organization_id) ON DELETE CASCADE,
            name VARCHAR(120) NOT NULL,
            key_prefix VARCHAR(32) NOT NULL UNIQUE,
            secret_hash VARCHAR(64) NOT NULL UNIQUE,
            scopes JSONB NOT NULL DEFAULT '[]'::jsonb,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            expires_at TIMESTAMP WITHOUT TIME ZONE,
            last_used_at TIMESTAMP WITHOUT TIME ZONE,
            revoked_at TIMESTAMP WITHOUT TIME ZONE,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_keys_user_active ON api_keys(user_id, active)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS api_usage_ledger (
            usage_id BIGSERIAL PRIMARY KEY,
            key_id VARCHAR(36) REFERENCES api_keys(key_id) ON DELETE SET NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            route VARCHAR(180) NOT NULL,
            status_code INTEGER NOT NULL,
            request_id VARCHAR(64),
            latency_ms DOUBLE PRECISION,
            occurred_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_usage_key_time ON api_usage_ledger(key_id, occurred_at DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS webhook_deliveries (
            webhook_delivery_id VARCHAR(36) PRIMARY KEY,
            webhook_endpoint_id VARCHAR(36) NOT NULL REFERENCES webhook_endpoints(webhook_endpoint_id) ON DELETE CASCADE,
            event_id VARCHAR(64) NOT NULL,
            event_type VARCHAR(96) NOT NULL,
            payload JSONB NOT NULL,
            idempotency_key VARCHAR(128) NOT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'pending',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            response_status INTEGER,
            response_excerpt VARCHAR(500),
            last_error VARCHAR(500),
            delivered_at TIMESTAMP WITHOUT TIME ZONE,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_webhook_delivery_idempotency UNIQUE(webhook_endpoint_id, idempotency_key)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_webhook_delivery_pending ON webhook_deliveries(status, next_attempt_at)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS organization_invitations (
            invitation_id VARCHAR(36) PRIMARY KEY,
            organization_id VARCHAR(36) NOT NULL REFERENCES organizations(organization_id) ON DELETE CASCADE,
            email VARCHAR(320) NOT NULL,
            role VARCHAR(32) NOT NULL DEFAULT 'viewer',
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            status VARCHAR(24) NOT NULL DEFAULT 'pending',
            invited_by INTEGER NOT NULL REFERENCES users(id),
            expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            accepted_by INTEGER REFERENCES users(id),
            accepted_at TIMESTAMP WITHOUT TIME ZONE,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_org_invitations_org ON organization_invitations(organization_id, status)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS support_tickets (
            ticket_id VARCHAR(36) PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            organization_id VARCHAR(36) REFERENCES organizations(organization_id) ON DELETE SET NULL,
            subject VARCHAR(180) NOT NULL,
            category VARCHAR(64) NOT NULL DEFAULT 'general',
            priority VARCHAR(24) NOT NULL DEFAULT 'normal',
            status VARCHAR(24) NOT NULL DEFAULT 'open',
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            closed_at TIMESTAMP WITHOUT TIME ZONE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_support_tickets_user ON support_tickets(user_id, created_at DESC)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS support_messages (
            message_id VARCHAR(36) PRIMARY KEY,
            ticket_id VARCHAR(36) NOT NULL REFERENCES support_tickets(ticket_id) ON DELETE CASCADE,
            author_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            author_role VARCHAR(32) NOT NULL DEFAULT 'user',
            message TEXT NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS analytics_events (
            event_id VARCHAR(36) PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            organization_id VARCHAR(36) REFERENCES organizations(organization_id) ON DELETE SET NULL,
            anonymous_id VARCHAR(64),
            event_name VARCHAR(96) NOT NULL,
            source VARCHAR(32) NOT NULL,
            session_id VARCHAR(36),
            properties JSONB NOT NULL DEFAULT '{}'::jsonb,
            occurred_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            ingested_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_analytics_event_name_time ON analytics_events(event_name, occurred_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_analytics_user_time ON analytics_events(user_id, occurred_at DESC)")


def downgrade() -> None:
    # Preserve user-generated journals, support records and access audit history.
    pass
