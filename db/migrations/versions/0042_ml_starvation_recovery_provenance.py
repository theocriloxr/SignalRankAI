"""persist ML starvation recovery provenance on signals

Revision ID: 0042_ml_starvation_recovery_provenance
Revises: 0041_broker_connection_registry
"""
from __future__ import annotations

from alembic import op

revision = "0042_ml_starvation_recovery_provenance"
down_revision = "0041_broker_connection_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE signals "
        "ADD COLUMN IF NOT EXISTS ml_recovery_mode BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE signals "
        "ADD COLUMN IF NOT EXISTS ml_recovery_reason VARCHAR(64)"
    )
    op.execute(
        "ALTER TABLE signals "
        "ADD COLUMN IF NOT EXISTS ml_recovery_champion_raw_probability DOUBLE PRECISION"
    )
    op.execute(
        "ALTER TABLE signals "
        "ADD COLUMN IF NOT EXISTS ml_recovery_certified_threshold DOUBLE PRECISION"
    )
    op.execute(
        "ALTER TABLE signals "
        "ADD COLUMN IF NOT EXISTS ml_recovery_challenger_probability DOUBLE PRECISION"
    )
    op.execute(
        "ALTER TABLE signals "
        "ADD COLUMN IF NOT EXISTS ml_recovery_challenger_threshold DOUBLE PRECISION"
    )
    op.execute(
        "ALTER TABLE signals "
        "ADD COLUMN IF NOT EXISTS ml_recovery_challenger_version VARCHAR(64)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_signals_ml_recovery_mode "
        "ON signals(ml_recovery_mode,created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_signals_ml_recovery_mode")
    for column in (
        "ml_recovery_challenger_version",
        "ml_recovery_challenger_threshold",
        "ml_recovery_challenger_probability",
        "ml_recovery_certified_threshold",
        "ml_recovery_champion_raw_probability",
        "ml_recovery_reason",
        "ml_recovery_mode",
    ):
        op.execute(f"ALTER TABLE signals DROP COLUMN IF EXISTS {column}")
