"""add outcome truth columns and signal delivery send-state

Revision ID: 0023_outcome_truth_and_delivery_state
Revises: 0022_timeseries_partition_tables
Create Date: 2026-04-09
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0023_outcome_truth_and_delivery_state"
down_revision = "0022_timeseries_partition_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS canonical_outcome VARCHAR(16);")
    op.execute("ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS vip_fill_outcome VARCHAR(16);")
    op.execute("ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS sentiment_outcome VARCHAR(16);")

    op.execute("CREATE INDEX IF NOT EXISTS ix_outcomes_canonical_outcome ON outcomes(canonical_outcome);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_outcomes_vip_fill_outcome ON outcomes(vip_fill_outcome);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_outcomes_sentiment_outcome ON outcomes(sentiment_outcome);")

    op.execute("ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS sent_ok BOOLEAN NOT NULL DEFAULT FALSE;")
    op.execute("ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 1;")
    op.execute("ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMP NULL;")
    op.execute("ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS last_error TEXT NULL;")

    op.execute("CREATE INDEX IF NOT EXISTS ix_signal_deliveries_sent_ok ON signal_deliveries(sent_ok);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_signal_deliveries_sent_ok;")
    op.execute("ALTER TABLE signal_deliveries DROP COLUMN IF EXISTS last_error;")
    op.execute("ALTER TABLE signal_deliveries DROP COLUMN IF EXISTS last_attempt_at;")
    op.execute("ALTER TABLE signal_deliveries DROP COLUMN IF EXISTS attempt_count;")
    op.execute("ALTER TABLE signal_deliveries DROP COLUMN IF EXISTS sent_ok;")

    op.execute("DROP INDEX IF EXISTS ix_outcomes_sentiment_outcome;")
    op.execute("DROP INDEX IF EXISTS ix_outcomes_vip_fill_outcome;")
    op.execute("DROP INDEX IF EXISTS ix_outcomes_canonical_outcome;")
    op.execute("ALTER TABLE outcomes DROP COLUMN IF EXISTS sentiment_outcome;")
    op.execute("ALTER TABLE outcomes DROP COLUMN IF EXISTS vip_fill_outcome;")
    op.execute("ALTER TABLE outcomes DROP COLUMN IF EXISTS canonical_outcome;")
