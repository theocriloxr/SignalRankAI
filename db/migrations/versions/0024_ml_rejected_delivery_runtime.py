"""Repair rejection telemetry schema and delivery-runtime admission contract.

Revision ID: 0024_ml_rejected_delivery
Revises: 0023_signal_runtime_schema
Create Date: 2026-07-28

Railway's first live engine cycle proved that the canonical MLRejectedSignal
ORM includes ``signal_id`` while the historical migration/auto-op table did
not.  This forward-only repair is idempotent on clean and upgraded databases.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0024_ml_rejected_delivery"
down_revision = "0023_signal_runtime_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = str(bind.dialect.name or "").lower()
    if dialect == "postgresql":
        bind.execute(sa.text(
            "ALTER TABLE ml_rejected_signals "
            "ADD COLUMN IF NOT EXISTS signal_id VARCHAR(36)"
        ))
        bind.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_ml_rejected_signals_signal_id "
            "ON ml_rejected_signals (signal_id)"
        ))
        return

    inspector = sa.inspect(bind)
    columns = {str(c.get("name") or "").lower() for c in inspector.get_columns("ml_rejected_signals")}
    if "signal_id" not in columns:
        op.add_column("ml_rejected_signals", sa.Column("signal_id", sa.String(36), nullable=True))
    indexes = {str(i.get("name") or "") for i in inspector.get_indexes("ml_rejected_signals")}
    if "ix_ml_rejected_signals_signal_id" not in indexes:
        op.create_index("ix_ml_rejected_signals_signal_id", "ml_rejected_signals", ["signal_id"])


def downgrade() -> None:
    # Forward-only evidence schema repair. Historical rejection rows are retained.
    pass
