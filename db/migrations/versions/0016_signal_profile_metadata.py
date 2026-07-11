"""add signal profile routing metadata

Revision ID: 0016_signal_profile_metadata
Revises: 0015_active_signal_guard
Create Date: 2026-07-03
"""

from alembic import op


revision = "0016_signal_profile_metadata"
down_revision = "0015_active_signal_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE signals ADD COLUMN IF NOT EXISTS trade_profile VARCHAR(16)")
    op.execute("ALTER TABLE signals ADD COLUMN IF NOT EXISTS asset_class VARCHAR(16)")
    op.execute("ALTER TABLE signals ADD COLUMN IF NOT EXISTS target_model VARCHAR(32)")
    op.execute("ALTER TABLE signals ADD COLUMN IF NOT EXISTS expected_duration VARCHAR(64)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_signals_trade_profile ON signals (trade_profile)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_signals_asset_class ON signals (asset_class)")


def downgrade() -> None:
    op.drop_index("ix_signals_asset_class", table_name="signals")
    op.drop_index("ix_signals_trade_profile", table_name="signals")
    op.drop_column("signals", "expected_duration")
    op.drop_column("signals", "target_model")
    op.drop_column("signals", "asset_class")
    op.drop_column("signals", "trade_profile")
