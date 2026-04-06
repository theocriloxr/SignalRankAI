"""Outcome per-recipient delivery state and idempotency.

Revision ID: 0012_outcome_notify_state
Revises: 0011_platform_harden_security
Create Date: 2026-04-06
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0012_outcome_notify_state"
down_revision = "0011_platform_harden_security"
branch_labels = None
depends_on = None


def _exec(sql: str) -> None:
    op.execute(sa.text(sql))


def upgrade() -> None:
    _exec(
        """
        CREATE TABLE IF NOT EXISTS outcome_notifications (
            id SERIAL PRIMARY KEY,
            outcome_id INTEGER NOT NULL REFERENCES outcomes(id) ON DELETE CASCADE,
            signal_id VARCHAR(36) NOT NULL REFERENCES signals(signal_id) ON DELETE CASCADE,
            telegram_user_id BIGINT NOT NULL,
            tier_at_send VARCHAR(16) NOT NULL DEFAULT 'free',
            outcome_status VARCHAR(16) NOT NULL,
            idempotency_key VARCHAR(128) NOT NULL,
            delivery_state VARCHAR(16) NOT NULL DEFAULT 'pending',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_attempt_at TIMESTAMP NULL,
            delivered_at TIMESTAMP NULL,
            last_error TEXT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_outcome_notifications_idempotency_key UNIQUE (idempotency_key),
            CONSTRAINT uq_outcome_notifications_sig_user_status UNIQUE (signal_id, telegram_user_id, outcome_status)
        )
        """
    )
    _exec("CREATE INDEX IF NOT EXISTS ix_outcome_notifications_outcome_id ON outcome_notifications (outcome_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_outcome_notifications_signal_id ON outcome_notifications (signal_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_outcome_notifications_telegram_user_id ON outcome_notifications (telegram_user_id)")
    _exec("CREATE INDEX IF NOT EXISTS ix_outcome_notifications_outcome_status ON outcome_notifications (outcome_status)")
    _exec("CREATE INDEX IF NOT EXISTS ix_outcome_notifications_delivery_state ON outcome_notifications (delivery_state)")
    _exec("CREATE INDEX IF NOT EXISTS ix_outcome_notifications_delivered_at ON outcome_notifications (delivered_at)")

    # Seed queue for historical outcomes not explicitly marked as notified.
    _exec(
        """
        INSERT INTO outcome_notifications (
            outcome_id, signal_id, telegram_user_id, tier_at_send, outcome_status,
            idempotency_key, delivery_state, created_at, updated_at
        )
        SELECT
            o.id AS outcome_id,
            o.signal_id,
            u.telegram_user_id,
            sd.tier_at_send,
            lower(o.status) AS outcome_status,
            'outcome:' || o.signal_id || ':' || u.telegram_user_id::text || ':' || lower(o.status) AS idempotency_key,
            CASE
                WHEN COALESCE((o.meta->>'notified')::boolean, false) THEN 'delivered'
                ELSE 'pending'
            END AS delivery_state,
            NOW(),
            NOW()
        FROM outcomes o
        JOIN signal_deliveries sd ON sd.signal_id = o.signal_id
        JOIN users u ON u.id = sd.user_id
        WHERE o.closed_at IS NOT NULL
        ON CONFLICT (idempotency_key) DO NOTHING
        """
    )
    _exec(
        """
        UPDATE outcome_notifications n
        SET
            delivered_at = COALESCE(
                n.delivered_at,
                NULLIF((o.meta->>'notified_at'), '')::timestamp
            ),
            updated_at = NOW()
        FROM outcomes o
        WHERE n.outcome_id = o.id
          AND n.delivery_state = 'delivered'
        """
    )


def downgrade() -> None:
    _exec("DROP INDEX IF EXISTS ix_outcome_notifications_delivered_at")
    _exec("DROP INDEX IF EXISTS ix_outcome_notifications_delivery_state")
    _exec("DROP INDEX IF EXISTS ix_outcome_notifications_outcome_status")
    _exec("DROP INDEX IF EXISTS ix_outcome_notifications_telegram_user_id")
    _exec("DROP INDEX IF EXISTS ix_outcome_notifications_signal_id")
    _exec("DROP INDEX IF EXISTS ix_outcome_notifications_outcome_id")
    _exec("DROP TABLE IF EXISTS outcome_notifications")
