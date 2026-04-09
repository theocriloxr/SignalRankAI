"""Create proxy_nodes table for dynamic proxy pool.

Revision ID: 0013_proxy_nodes
Revises: 0012_outcome_notify_state
Create Date: 2026-04-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0013_proxy_nodes"
down_revision = "0012_outcome_notify_state"
branch_labels = None
depends_on = None


def _exec(sql: str) -> None:
    op.execute(sa.text(sql))


def upgrade() -> None:
    _exec("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    _exec(
        """
        CREATE TABLE IF NOT EXISTS proxy_nodes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            proxy_url VARCHAR(512) NOT NULL UNIQUE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            fail_count INTEGER NOT NULL DEFAULT 0,
            last_checked TIMESTAMP NULL,
            latency_ms DOUBLE PRECISION NULL
        )
        """
    )
    _exec("CREATE INDEX IF NOT EXISTS ix_proxy_nodes_proxy_url ON proxy_nodes (proxy_url)")
    _exec("CREATE INDEX IF NOT EXISTS ix_proxy_nodes_is_active ON proxy_nodes (is_active)")


def downgrade() -> None:
    _exec("DROP INDEX IF EXISTS ix_proxy_nodes_is_active")
    _exec("DROP INDEX IF EXISTS ix_proxy_nodes_proxy_url")
    _exec("DROP TABLE IF EXISTS proxy_nodes")
