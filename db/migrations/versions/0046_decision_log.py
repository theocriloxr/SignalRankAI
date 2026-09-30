"""Unify rejected signals and pulse metrics into a comprehensive decision_log.

Revision ID: 0046_decision_log
Revises: 0045_mt5_credential_retirement
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0046_decision_log"
down_revision = "0045_mt5_credential_retirement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Ensure the unified decision_log table exists (it is also created by auto_ops)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS decision_log (
            id SERIAL PRIMARY KEY,
            signal_id VARCHAR(36),
            asset VARCHAR(32),
            timeframe VARCHAR(8),
            decision VARCHAR(32) NOT NULL,
            reason TEXT,
            meta JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    
    # 2. Add any missing indexes
    op.execute("CREATE INDEX IF NOT EXISTS ix_decision_log_signal_id ON decision_log(signal_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_decision_log_asset ON decision_log(asset)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_decision_log_timeframe ON decision_log(timeframe)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_decision_log_decision ON decision_log(decision)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_decision_log_created_at ON decision_log(created_at)")

    # 3. Migrate existing data from ml_rejected_signals to decision_log if the table still exists
    # We use a DO block to avoid errors if the table is already gone.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'ml_rejected_signals') THEN
                INSERT INTO decision_log (
                    signal_id, asset, timeframe, decision, reason, meta, created_at
                )
                SELECT 
                    signal_id, asset, timeframe, 'rejected' AS decision, rejection_reason AS reason, 
                    jsonb_build_object(
                        'layer', 'ml',
                        'direction', direction,
                        'entry', entry,
                        'stop_loss', stop_loss,
                        'take_profit', take_profit,
                        'ml_probability', ml_probability,
                        'features', features,
                        'actual_outcome', actual_outcome,
                        'outcome_tracked_at', outcome_tracked_at
                    ) AS meta,
                    created_at
                FROM ml_rejected_signals;
                
                DROP TABLE ml_rejected_signals CASCADE;
            END IF;
        END $$;
        """
    )

    # 4. Create the backward-compatible view for ml_rejected_signals
    # This prevents us from having to refactor 10+ files immediately.
    op.execute(
        """
        CREATE OR REPLACE VIEW ml_rejected_signals AS
        SELECT 
            id,
            signal_id,
            asset,
            timeframe,
            meta->>'direction' AS direction,
            CAST(meta->>'entry' AS DOUBLE PRECISION) AS entry,
            CAST(meta->>'stop_loss' AS DOUBLE PRECISION) AS stop_loss,
            meta->>'take_profit' AS take_profit,
            CAST(meta->>'ml_probability' AS DOUBLE PRECISION) AS ml_probability,
            reason AS rejection_reason,
            COALESCE(meta->'features', '{}'::jsonb) AS features,
            meta->>'actual_outcome' AS actual_outcome,
            CAST(meta->>'outcome_tracked_at' AS TIMESTAMP) AS outcome_tracked_at,
            created_at
        FROM decision_log
        WHERE meta->>'layer' = 'ml' AND decision = 'rejected'
        """
    )


def downgrade() -> None:
    # No-op downgrade for data migration, to avoid losing telemetry data.
    pass
