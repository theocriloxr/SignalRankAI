"""adaptive operational hotfix and schema compatibility repair

Revision ID: 0026_adaptive_operational_hotfix
Revises: 0025_adaptive_strategy
Create Date: 2026-07-28
"""
from alembic import op

revision = "0026_adaptive_operational_hotfix"
down_revision = "0025_adaptive_strategy"
branch_labels = None
depends_on = None


def upgrade():
    # 0025 uses started_at. Repair databases where an early/manual table exists.
    op.execute(
        "ALTER TABLE adaptive_walk_forward_runs "
        "ADD COLUMN IF NOT EXISTS started_at TIMESTAMP NOT NULL DEFAULT NOW()"
    )
    op.execute("DROP INDEX IF EXISTS ix_adaptive_wfo_profile_dataset")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_adaptive_wfo_profile_dataset "
        "ON adaptive_walk_forward_runs(profile_id,dataset_version,started_at DESC)"
    )

    # Older auto-created decision_log tables did not always contain created_at.
    op.execute(
        "ALTER TABLE decision_log "
        "ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW()"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_decision_log_created_at "
        "ON decision_log(created_at DESC)"
    )

    # Short Telegram references are resolved with a prefix query.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_signals_signal_id_prefix "
        "ON signals (signal_id varchar_pattern_ops)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_signals_signal_id_prefix")
    # created_at may pre-date this migration; do not destructively remove it.
    op.execute("DROP INDEX IF EXISTS ix_adaptive_wfo_profile_dataset")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_adaptive_wfo_profile_dataset "
        "ON adaptive_walk_forward_runs(profile_id,dataset_version,started_at DESC)"
    )
