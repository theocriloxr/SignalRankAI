"""Add non-blocking production indexes for signal delivery paths.

Revision ID: 0017_concurrent_signal_delivery_indexes
Revises: 0016_add_strategy_regime_columns
Create Date: 2026-07-11 00:00:00.000000

All indexes in this migration use PostgreSQL CREATE INDEX CONCURRENTLY to avoid
blocking active signal/delivery tables during Railway production deploys.
"""
from alembic import op

revision = "0017_concurrent_signal_delivery_indexes"
down_revision = "0016_add_strategy_regime_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        op.create_index("ix_signals_asset_tf_status_created", "signals", ["asset", "timeframe", "status", "created_at"], if_not_exists=True)
        op.create_index("ix_signal_deliveries_user_sent_created", "signal_deliveries", ["user_id", "sent_ok", "delivered_at"], if_not_exists=True)
        op.create_index("ix_signal_deliveries_signal_sent_created", "signal_deliveries", ["signal_id", "sent_ok", "delivered_at"], if_not_exists=True)
        op.create_index("ix_active_signal_messages_user_signal_active", "active_signal_messages", ["user_id", "signal_id", "is_active"], if_not_exists=True)
        return

    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_signals_asset_tf_status_created "
            "ON signals (asset, timeframe, status, created_at DESC)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_signals_status_created "
            "ON signals (status, created_at DESC)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_signal_deliveries_user_sent_created "
            "ON signal_deliveries (user_id, sent_ok, delivered_at DESC)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_signal_deliveries_signal_sent_created "
            "ON signal_deliveries (signal_id, sent_ok, delivered_at DESC)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_active_signal_messages_user_signal_active "
            "ON active_signal_messages (user_id, signal_id, is_active)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        op.drop_index("ix_active_signal_messages_user_signal_active", table_name="active_signal_messages", if_exists=True)
        op.drop_index("ix_signal_deliveries_signal_sent_created", table_name="signal_deliveries", if_exists=True)
        op.drop_index("ix_signal_deliveries_user_sent_created", table_name="signal_deliveries", if_exists=True)
        op.drop_index("ix_signals_status_created", table_name="signals", if_exists=True)
        op.drop_index("ix_signals_asset_tf_status_created", table_name="signals", if_exists=True)
        return

    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_active_signal_messages_user_signal_active")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_signal_deliveries_signal_sent_created")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_signal_deliveries_user_sent_created")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_signals_status_created")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_signals_asset_tf_status_created")
