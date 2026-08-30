"""production integrity hardening

Revision ID: 0034_production_integrity
Revises: 0033_ml_learning_runtime
Create Date: 2026-08-02
"""
from alembic import op

revision = "0034_production_integrity"
down_revision = "0033_ml_learning_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The thesis fingerprint backfill uses digest().  Declare the dependency in
    # this migration rather than relying on a historical extension migration.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("ALTER TABLE signals ADD COLUMN IF NOT EXISTS thesis_fingerprint VARCHAR(64)")
    op.execute("ALTER TABLE signals ADD COLUMN IF NOT EXISTS asset_discovery_provider VARCHAR(128)")
    op.execute("ALTER TABLE signals ADD COLUMN IF NOT EXISTS ml_probability_raw DOUBLE PRECISION")
    op.execute("ALTER TABLE signals ADD COLUMN IF NOT EXISTS ml_probability_calibrated DOUBLE PRECISION")
    op.execute("ALTER TABLE signals ADD COLUMN IF NOT EXISTS ml_calibration_version VARCHAR(64)")
    op.execute("ALTER TABLE signals ADD COLUMN IF NOT EXISTS ml_calibration_validated BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE signals ADD COLUMN IF NOT EXISTS ml_calibration_validation_rows INTEGER")
    op.execute("ALTER TABLE signals ADD COLUMN IF NOT EXISTS ml_calibration_brier DOUBLE PRECISION")
    op.execute("ALTER TABLE signals ADD COLUMN IF NOT EXISTS ml_calibration_ece DOUBLE PRECISION")
    op.execute("ALTER TABLE signals ADD COLUMN IF NOT EXISTS quality_gate_version VARCHAR(64)")
    op.execute("ALTER TABLE signals ADD COLUMN IF NOT EXISTS quality_gate_passed BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("CREATE INDEX IF NOT EXISTS ix_signals_thesis_fingerprint ON signals (thesis_fingerprint)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_signals_asset_discovery_provider ON signals (asset_discovery_provider)")
    op.execute("ALTER TABLE performance_ledger_entries ADD COLUMN IF NOT EXISTS thesis_fingerprint VARCHAR(64)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_performance_ledger_thesis ON performance_ledger_entries (thesis_fingerprint)")
    op.execute("ALTER TABLE outcome_notifications ADD COLUMN IF NOT EXISTS stage_rank INTEGER NOT NULL DEFAULT 0")
    op.execute("CREATE INDEX IF NOT EXISTS ix_outcome_notifications_stage_rank ON outcome_notifications (stage_rank)")
    # Reconcile duplicate open paper positions before enforcing uniqueness. The
    # migration returns reserved virtual cash and current unrealized P&L to the
    # account so cleanup cannot silently destroy paper equity.
    op.execute("""
        CREATE TEMP TABLE tmp_duplicate_paper_positions ON COMMIT DROP AS
        SELECT p.*
        FROM (
            SELECT position_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY user_id, UPPER(asset)
                       ORDER BY opened_at DESC, created_at DESC
                   ) AS rn
            FROM paper_positions
            WHERE LOWER(status) = 'open'
        ) ranked
        JOIN paper_positions p ON p.position_id = ranked.position_id
        WHERE ranked.rn > 1
    """)
    op.execute("""
        UPDATE paper_accounts a
        SET cash_balance = a.cash_balance + x.release_cash,
            realized_pnl = a.realized_pnl + x.net_pnl,
            updated_at = NOW()
        FROM (
            SELECT account_id,
                   SUM(COALESCE(reserved_cash, 0) + COALESCE(unrealized_pnl, 0)) AS release_cash,
                   SUM(COALESCE(unrealized_pnl, 0) - COALESCE(entry_fee, 0)) AS net_pnl
            FROM tmp_duplicate_paper_positions
            GROUP BY account_id
        ) x
        WHERE a.id = x.account_id
    """)
    op.execute("""
        UPDATE paper_positions p
        SET status = 'closed',
            closed_at = COALESCE(p.closed_at, NOW()),
            exit_reason = 'duplicate_asset_reconciled',
            exit_fee = 0,
            realized_pnl = COALESCE(p.unrealized_pnl, 0) - COALESCE(p.entry_fee, 0),
            r_multiple = CASE
                WHEN ABS((p.fill_entry - p.stop_loss) * p.quantity) > 0
                THEN (COALESCE(p.unrealized_pnl, 0) - COALESCE(p.entry_fee, 0)) /
                     ABS((p.fill_entry - p.stop_loss) * p.quantity)
                ELSE 0
            END,
            unrealized_pnl = 0,
            updated_at = NOW()
        FROM tmp_duplicate_paper_positions d
        WHERE p.position_id = d.position_id
    """)
    op.execute("""
        INSERT INTO paper_ledger_entries (
            account_id, user_id, position_id, entry_type, amount,
            balance_after, description, meta, created_at
        )
        SELECT d.account_id, d.user_id, d.position_id, 'DUPLICATE_RECONCILED',
               COALESCE(d.reserved_cash, 0) + COALESCE(d.unrealized_pnl, 0),
               a.cash_balance,
               'Closed duplicate open paper position during production-integrity migration',
               jsonb_build_object('asset', d.asset, 'reason', 'duplicate_asset_reconciled'),
               NOW()
        FROM tmp_duplicate_paper_positions d
        JOIN paper_accounts a ON a.id = d.account_id
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_open_user_asset
        ON paper_positions (user_id, UPPER(asset))
        WHERE LOWER(status) = 'open'
    """)
    # Backfill stable fingerprints for existing signals using stored identity.
    op.execute("""
        UPDATE signals
        SET thesis_fingerprint = encode(digest(
            UPPER(COALESCE(asset,'')) || '|' || LOWER(COALESCE(direction,'')) || '|' ||
            LOWER(COALESCE(strategy_name,'unknown')) || '|' || LOWER(COALESCE(regime,'unknown')),
            'sha256'), 'hex')
        WHERE thesis_fingerprint IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_paper_open_user_asset")
    op.execute("DROP INDEX IF EXISTS ix_outcome_notifications_stage_rank")
    op.execute("ALTER TABLE outcome_notifications DROP COLUMN IF EXISTS stage_rank")
    op.execute("DROP INDEX IF EXISTS ix_performance_ledger_thesis")
    op.execute("ALTER TABLE performance_ledger_entries DROP COLUMN IF EXISTS thesis_fingerprint")
    op.execute("DROP INDEX IF EXISTS ix_signals_asset_discovery_provider")
    op.execute("ALTER TABLE signals DROP COLUMN IF EXISTS asset_discovery_provider")
    op.execute("DROP INDEX IF EXISTS ix_signals_thesis_fingerprint")
    op.execute("ALTER TABLE signals DROP COLUMN IF EXISTS quality_gate_passed")
    op.execute("ALTER TABLE signals DROP COLUMN IF EXISTS quality_gate_version")
    op.execute("ALTER TABLE signals DROP COLUMN IF EXISTS ml_calibration_ece")
    op.execute("ALTER TABLE signals DROP COLUMN IF EXISTS ml_calibration_brier")
    op.execute("ALTER TABLE signals DROP COLUMN IF EXISTS ml_calibration_validation_rows")
    op.execute("ALTER TABLE signals DROP COLUMN IF EXISTS ml_calibration_validated")
    op.execute("ALTER TABLE signals DROP COLUMN IF EXISTS ml_calibration_version")
    op.execute("ALTER TABLE signals DROP COLUMN IF EXISTS ml_probability_calibrated")
    op.execute("ALTER TABLE signals DROP COLUMN IF EXISTS ml_probability_raw")
    op.execute("ALTER TABLE signals DROP COLUMN IF EXISTS thesis_fingerprint")
