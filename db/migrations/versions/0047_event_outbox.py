"""Durable event outbox for Redis outage recovery.

Revision ID: 0047_event_outbox
Revises: 0046_decision_log
"""

from __future__ import annotations

from alembic import op

revision = "0047_event_outbox"
down_revision = "0046_decision_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS event_outbox (
            entry_id VARCHAR(96) PRIMARY KEY,
            event_type VARCHAR(128) NOT NULL,
            partition_key VARCHAR(256) NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            idempotency_key VARCHAR(256) NOT NULL UNIQUE,
            occurred_at TIMESTAMPTZ NOT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            claimed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_event_outbox_claim "
        "ON event_outbox(status, available_at, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_event_outbox_partition "
        "ON event_outbox(partition_key, created_at)"
    )


def downgrade() -> None:
    # Preserve pending/delivery evidence on downgrade. Operators may archive
    # explicitly after confirming no rows remain claimable.
    pass
