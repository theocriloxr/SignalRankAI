"""runtime state

Revision ID: 0003_runtime_state
Revises: 0002_features
Create Date: 2026-01-01

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0003_runtime_state"
down_revision = "0002_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_state",
        sa.Column("key", sa.String(length=128), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_runtime_state_expires_at", "runtime_state", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_runtime_state_expires_at", table_name="runtime_state")
    op.drop_table("runtime_state")
