"""canonical performance ledger and retryable paper trade attempts

Revision ID: 0031_perf_paper_reliability
Revises: 0030_signal_monitor_reliability
Create Date: 2026-08-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0031_perf_paper_reliability"
down_revision = "0030_signal_monitor_reliability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in (
        "ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS terminal_version INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS provenance VARCHAR(32) NOT NULL DEFAULT 'canonical_live'",
        "ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS calculation_policy_version VARCHAR(64) NOT NULL DEFAULT 'legacy'",
        "ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS performance_inclusion_status VARCHAR(24) NOT NULL DEFAULT 'eligible'",
        "ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS performance_exclusion_reason VARCHAR(128)",
        "ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS corrected_at TIMESTAMP WITHOUT TIME ZONE",
        "ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS corrected_by VARCHAR(128)",
        "ALTER TABLE outcomes ADD COLUMN IF NOT EXISTS correction_reason TEXT",
    ):
        op.execute(statement)
    op.execute("""
        UPDATE outcomes
        SET terminal_version = 1
        WHERE terminal_version = 0
          AND LOWER(COALESCE(canonical_outcome, status, '')) IN
              ('tp','tp3','win','sl','loss','stop','stop_loss','be','breakeven','break_even','time_stop')
    """)

    op.create_table(
        "paper_trade_attempts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("attempt_id", sa.String(36), nullable=False, unique=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("paper_accounts.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("signal_id", sa.String(36), sa.ForeignKey("signals.signal_id"), nullable=False),
        sa.Column("delivery_id", sa.Integer(), sa.ForeignKey("signal_deliveries.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(128), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("market_price", sa.Float()),
        sa.Column("available_cash", sa.Float()),
        sa.Column("risk_amount", sa.Float()),
        sa.Column("calculated_quantity", sa.Float()),
        sa.Column("calculated_notional", sa.Float()),
        sa.Column("calculated_fee", sa.Float()),
        sa.Column("required_cash", sa.Float()),
        sa.Column("sizing_policy_version", sa.String(64), nullable=False, server_default="paper-fee-reserve-v2"),
        sa.Column("first_attempt_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("next_retry_at", sa.DateTime()),
        sa.Column("retry_deadline", sa.DateTime()),
        sa.Column("finalized_at", sa.DateTime()),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("idempotency_key", name="uq_paper_trade_attempt_key"),
    )
    for name, columns in (
        ("ix_paper_attempt_account", ["account_id"]),
        ("ix_paper_attempt_user_signal", ["user_id", "signal_id"]),
        ("ix_paper_attempt_delivery", ["delivery_id"]),
        ("ix_paper_attempt_decision_reason", ["decision", "reason"]),
        ("ix_paper_attempt_retry_scan", ["retryable", "next_retry_at", "retry_deadline"]),
    ):
        op.create_index(name, "paper_trade_attempts", columns)

    # Preserve legacy skipped rows as auditable attempts. They remain in place;
    # the partial position index allows a later genuine position without erasure.
    op.execute("""
        INSERT INTO paper_trade_attempts (
            attempt_id, account_id, user_id, signal_id, delivery_id,
            idempotency_key, decision, reason, retryable, attempt_number,
            market_price, available_cash, calculated_quantity,
            calculated_notional, calculated_fee, required_cash,
            sizing_policy_version, first_attempt_at, last_attempt_at,
            finalized_at, meta, created_at, updated_at
        )
        SELECT
            md5(pp.position_id || ':0031')::uuid::text,
            pp.account_id, pp.user_id, pp.signal_id, pp.delivery_id,
            'legacy-paper-position:' || pp.position_id,
            'SKIPPED', COALESCE(pp.exit_reason, 'legacy_skip'), false, 1,
            pp.current_price, pa.cash_balance, pp.quantity,
            pp.notional, pp.entry_fee, pp.notional + pp.entry_fee,
            'legacy-pre-fee-reserve', pp.created_at, pp.updated_at,
            COALESCE(pp.closed_at, pp.updated_at),
            json_build_object('legacy_position_id', pp.position_id, 'preserved', true),
            pp.created_at, pp.updated_at
        FROM paper_positions pp
        JOIN paper_accounts pa ON pa.id = pp.account_id
        WHERE LOWER(pp.status) = 'skipped'
        ON CONFLICT (idempotency_key) DO NOTHING
    """)
    op.drop_constraint("uq_paper_position_user_signal", "paper_positions", type_="unique")
    op.execute("""
        CREATE UNIQUE INDEX uq_paper_actual_position_user_signal
        ON paper_positions (user_id, signal_id)
        WHERE LOWER(status) IN ('open', 'closed')
    """)

    op.create_table(
        "performance_ledger_entries",
        sa.Column("ledger_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("signal_id", sa.String(36), sa.ForeignKey("signals.signal_id"), nullable=False),
        sa.Column("delivery_id", sa.Integer(), sa.ForeignKey("signal_deliveries.id"), nullable=False),
        sa.Column("domain", sa.String(32), nullable=False),
        sa.Column("environment", sa.String(24), nullable=False),
        sa.Column("delivery_confirmed_at", sa.DateTime(), nullable=False),
        sa.Column("asset", sa.String(32), nullable=False),
        sa.Column("timeframe", sa.String(8), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("primary_bucket", sa.String(32), nullable=False),
        sa.Column("entry_status", sa.String(24), nullable=False),
        sa.Column("highest_tp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("global_outcome", sa.String(32)),
        sa.Column("user_monitoring_outcome", sa.String(32)),
        sa.Column("final_realized_r", sa.Float()),
        sa.Column("outcome_completed_at", sa.DateTime()),
        sa.Column("outcome_source", sa.String(32), nullable=False),
        sa.Column("calculation_policy_version", sa.String(64), nullable=False),
        sa.Column("signal_plan_version", sa.String(64), nullable=False),
        sa.Column("included", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("exclusion_reason", sa.String(128)),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("finalized_at", sa.DateTime()),
        sa.Column("corrected_at", sa.DateTime()),
        sa.Column("corrected_by", sa.String(128)),
        sa.Column("correction_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("user_id", "signal_id", "domain", "environment", name="uq_performance_ledger_scope"),
    )
    for name, columns in (
        ("ix_performance_ledger_user_delivery", ["user_id", "delivery_confirmed_at"]),
        ("ix_performance_ledger_signal", ["signal_id"]),
        ("ix_performance_ledger_domain_env", ["domain", "environment"]),
        ("ix_performance_ledger_bucket", ["primary_bucket"]),
        ("ix_performance_ledger_included", ["included"]),
        ("ix_performance_ledger_finalized", ["finalized_at"]),
    ):
        op.create_index(name, "performance_ledger_entries", columns)
    op.create_table(
        "performance_correction_audit",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ledger_id", sa.String(36), sa.ForeignKey("performance_ledger_entries.ledger_id"), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("before_values", sa.JSON(), nullable=False),
        sa.Column("after_values", sa.JSON(), nullable=False),
        sa.Column("tool_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_performance_correction_ledger", "performance_correction_audit", ["ledger_id"])

    op.execute("""
        CREATE OR REPLACE FUNCTION enforce_performance_ledger_finality()
        RETURNS trigger AS $$
        BEGIN
            IF OLD.finalized_at IS NOT NULL
               AND NEW.corrected_at IS NOT DISTINCT FROM OLD.corrected_at
               AND (
                    NEW.primary_bucket IS DISTINCT FROM OLD.primary_bucket OR
                    NEW.final_realized_r IS DISTINCT FROM OLD.final_realized_r OR
                    NEW.included IS DISTINCT FROM OLD.included OR
                    NEW.exclusion_reason IS DISTINCT FROM OLD.exclusion_reason OR
                    NEW.snapshot_hash IS DISTINCT FROM OLD.snapshot_hash
               ) THEN
                RAISE EXCEPTION 'finalized performance ledger row requires audited correction metadata';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_performance_ledger_finality
        BEFORE UPDATE ON performance_ledger_entries
        FOR EACH ROW EXECUTE FUNCTION enforce_performance_ledger_finality()
    """)

    # Repair databases that have the ORM path but missed the historical ML table.
    op.execute("""
        CREATE TABLE IF NOT EXISTS ml_past_training_data (
            id SERIAL PRIMARY KEY,
            signal_id VARCHAR(36) NOT NULL UNIQUE REFERENCES signals(signal_id),
            asset VARCHAR(32) NOT NULL,
            timeframe VARCHAR(8) NOT NULL,
            direction VARCHAR(8) NOT NULL,
            entry DOUBLE PRECISION NOT NULL,
            stop_loss DOUBLE PRECISION NOT NULL,
            take_profit TEXT NOT NULL,
            rr_estimate DOUBLE PRECISION,
            score DOUBLE PRECISION,
            strength DOUBLE PRECISION,
            regime VARCHAR(32),
            strategy_name VARCHAR(64),
            ml_probability DOUBLE PRECISION,
            outcome_status VARCHAR(16) NOT NULL,
            outcome_r_multiple DOUBLE PRECISION,
            outcome_percent DOUBLE PRECISION,
            outcome_meta JSON NOT NULL DEFAULT '{}'::json,
            signal_created_at TIMESTAMP WITHOUT TIME ZONE,
            outcome_closed_at TIMESTAMP WITHOUT TIME ZONE,
            archived_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    for statement in (
        "ALTER TABLE ml_past_training_data ADD COLUMN IF NOT EXISTS provenance_domain VARCHAR(32) NOT NULL DEFAULT 'legacy_unverified'",
        "ALTER TABLE ml_past_training_data ADD COLUMN IF NOT EXISTS delivery_proof_backed BOOLEAN NOT NULL DEFAULT false",
        "ALTER TABLE ml_past_training_data ADD COLUMN IF NOT EXISTS persistence_status VARCHAR(24) NOT NULL DEFAULT 'persisted'",
        "ALTER TABLE ml_past_training_data ADD COLUMN IF NOT EXISTS exclusion_reason VARCHAR(128)",
        "CREATE INDEX IF NOT EXISTS ix_ml_training_provenance ON ml_past_training_data (provenance_domain, delivery_proof_backed)",
    ):
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_performance_ledger_finality ON performance_ledger_entries")
    op.execute("DROP FUNCTION IF EXISTS enforce_performance_ledger_finality()")
    op.drop_table("performance_correction_audit")
    op.drop_table("performance_ledger_entries")
    op.execute("DROP INDEX IF EXISTS uq_paper_actual_position_user_signal")
    op.create_unique_constraint("uq_paper_position_user_signal", "paper_positions", ["user_id", "signal_id"])
    op.drop_table("paper_trade_attempts")
    for column in (
        "correction_reason", "corrected_by", "corrected_at",
        "performance_exclusion_reason", "performance_inclusion_status",
        "calculation_policy_version", "provenance", "terminal_version",
    ):
        op.drop_column("outcomes", column)
