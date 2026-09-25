"""multi-account execution, prop policy and decision provenance

Revision ID: 0043_account_execution_policy
Revises: 0042_ml_recovery_provenance
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0043_account_execution_policy"
down_revision = "0042_ml_recovery_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trading_account_policies",
        sa.Column("policy_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "connection_id",
            sa.String(length=64),
            sa.ForeignKey("broker_connections.connection_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("account_mode", sa.String(length=24), nullable=False, server_default="DEMO"),
        sa.Column(
            "execution_permission",
            sa.String(length=32),
            nullable=False,
            server_default="SIGNALS_ONLY",
        ),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="configured"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("reset_timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("max_risk_per_trade_pct", sa.Numeric(12, 8), nullable=False, server_default="0.005"),
        sa.Column("max_daily_loss_pct", sa.Numeric(12, 8), nullable=False, server_default="0.04"),
        sa.Column("max_weekly_loss_pct", sa.Numeric(12, 8), nullable=False, server_default="0.08"),
        sa.Column("max_total_drawdown_pct", sa.Numeric(12, 8), nullable=False, server_default="0.08"),
        sa.Column("max_open_positions", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("max_leverage", sa.Numeric(18, 8), nullable=False, server_default="1"),
        sa.Column("max_spread_bps", sa.Numeric(18, 8), nullable=False, server_default="50"),
        sa.Column("max_slippage_bps", sa.Numeric(18, 8), nullable=False, server_default="25"),
        sa.Column("min_confidence", sa.Numeric(12, 8), nullable=False, server_default="0"),
        sa.Column("min_expected_rr", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("safety_buffer_pct", sa.Numeric(12, 8), nullable=False, server_default="0"),
        sa.Column("external_max_daily_loss_pct", sa.Numeric(12, 8), nullable=True),
        sa.Column("external_max_weekly_loss_pct", sa.Numeric(12, 8), nullable=True),
        sa.Column("external_max_total_drawdown_pct", sa.Numeric(12, 8), nullable=True),
        sa.Column("allowed_instruments", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("allowed_asset_classes", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("allowed_strategies", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("trading_windows", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("news_trading_allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("weekend_holding_allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("prop_firm", sa.String(length=128), nullable=True),
        sa.Column("prop_phase", sa.String(length=64), nullable=True),
        sa.Column("prop_rules_version", sa.String(length=128), nullable=True),
        sa.Column("external_rules", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("certified_at", sa.DateTime(), nullable=True),
        sa.Column("certification_ref", sa.String(length=160), nullable=True),
        sa.Column("frozen_at", sa.DateTime(), nullable=True),
        sa.Column("frozen_reason", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("connection_id", name="uq_trading_account_policy_connection"),
        sa.CheckConstraint(
            "account_mode IN ('PAPER','DEMO','LIVE_PERSONAL','PROP')",
            name="ck_trading_account_policy_mode",
        ),
        sa.CheckConstraint(
            "execution_permission IN ('READ_ONLY','SIGNALS_ONLY','PAPER_ONLY','MANUAL','ASSISTED_EXECUTION','AUTO_EXECUTION')",
            name="ck_trading_account_policy_permission",
        ),
        sa.CheckConstraint("policy_version > 0", name="ck_trading_account_policy_version"),
        sa.CheckConstraint(
            "max_risk_per_trade_pct >= 0 AND max_risk_per_trade_pct <= 1",
            name="ck_trading_account_policy_risk",
        ),
        sa.CheckConstraint(
            "max_daily_loss_pct >= 0 AND max_daily_loss_pct <= 1",
            name="ck_trading_account_policy_daily_loss",
        ),
        sa.CheckConstraint(
            "max_weekly_loss_pct >= 0 AND max_weekly_loss_pct <= 1",
            name="ck_trading_account_policy_weekly_loss",
        ),
        sa.CheckConstraint(
            "max_total_drawdown_pct >= 0 AND max_total_drawdown_pct <= 1",
            name="ck_trading_account_policy_drawdown",
        ),
        sa.CheckConstraint("max_open_positions >= 0", name="ck_trading_account_policy_positions"),
        sa.CheckConstraint("max_leverage >= 0", name="ck_trading_account_policy_leverage"),
        sa.CheckConstraint("max_spread_bps >= 0", name="ck_trading_account_policy_spread"),
        sa.CheckConstraint("max_slippage_bps >= 0", name="ck_trading_account_policy_slippage"),
        sa.CheckConstraint("min_confidence >= 0 AND min_confidence <= 1", name="ck_trading_account_policy_confidence"),
        sa.CheckConstraint("min_expected_rr >= 0", name="ck_trading_account_policy_rr"),
        sa.CheckConstraint(
            "safety_buffer_pct >= 0 AND safety_buffer_pct <= 1",
            name="ck_trading_account_policy_buffer",
        ),
        sa.CheckConstraint(
            "external_max_daily_loss_pct IS NULL OR (external_max_daily_loss_pct > 0 AND external_max_daily_loss_pct <= 1)",
            name="ck_trading_account_policy_external_daily",
        ),
        sa.CheckConstraint(
            "external_max_weekly_loss_pct IS NULL OR (external_max_weekly_loss_pct > 0 AND external_max_weekly_loss_pct <= 1)",
            name="ck_trading_account_policy_external_weekly",
        ),
        sa.CheckConstraint(
            "external_max_total_drawdown_pct IS NULL OR (external_max_total_drawdown_pct > 0 AND external_max_total_drawdown_pct <= 1)",
            name="ck_trading_account_policy_external_drawdown",
        ),
    )
    op.create_index(
        "ix_trading_account_policy_user_mode",
        "trading_account_policies",
        ["user_id", "account_mode", "status"],
    )

    op.create_table(
        "broker_reconciliation_state",
        sa.Column(
            "connection_id",
            sa.String(length=64),
            sa.ForeignKey("broker_connections.connection_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="UNKNOWN"),
        sa.Column("discrepancy_code", sa.String(length=128), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("last_reconciled_at", sa.DateTime(), nullable=True),
        sa.Column("frozen_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "status IN ('UNKNOWN','HEALTHY','RECONCILING','DEGRADED','FROZEN','DISCONNECTED','AUTH_EXPIRED')",
            name="ck_broker_reconciliation_status",
        ),
    )
    op.create_index(
        "ix_broker_reconciliation_user_status",
        "broker_reconciliation_state",
        ["user_id", "status"],
    )

    op.create_table(
        "broker_execution_decisions",
        sa.Column("decision_id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "connection_id",
            sa.String(length=64),
            sa.ForeignKey("broker_connections.connection_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("signal_id", sa.String(length=36), nullable=False),
        sa.Column("execution_mode", sa.String(length=24), nullable=False),
        sa.Column("account_mode", sa.String(length=24), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("decision_status", sa.String(length=24), nullable=False),
        sa.Column("reason_codes", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("release_sha", sa.String(length=64), nullable=True),
        sa.Column("execution_engine_version", sa.String(length=64), nullable=True),
        sa.Column("model_versions", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("strategy_versions", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("market_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("risk_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("request_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index(
        "ix_broker_execution_decision_account_created",
        "broker_execution_decisions",
        ["connection_id", "created_at"],
    )
    op.create_index(
        "ix_broker_execution_decision_signal_user",
        "broker_execution_decisions",
        ["signal_id", "user_id"],
    )

    op.add_column(
        "broker_executions",
        sa.Column(
            "connection_id",
            sa.String(length=64),
            sa.ForeignKey("broker_connections.connection_id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_broker_executions_connection_status",
        "broker_executions",
        ["connection_id", "status"],
    )

    op.add_column(
        "mt5_executions",
        sa.Column(
            "connection_id",
            sa.String(length=64),
            sa.ForeignKey("broker_connections.connection_id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_mt5_executions_connection_status",
        "mt5_executions",
        ["connection_id", "status"],
    )

    # Historical MT5 rows retain their provider account ID. Backfill only when
    # that provider account maps to exactly one canonical connection for the
    # same user; ambiguous history remains NULL rather than being misattributed.
    op.execute(
        """
        UPDATE mt5_executions me
        SET connection_id = matched.connection_id
        FROM (
            SELECT bc.user_id, bc.external_account_id, MIN(bc.connection_id) AS connection_id
            FROM broker_connections bc
            WHERE bc.external_account_id IS NOT NULL
            GROUP BY bc.user_id, bc.external_account_id
            HAVING COUNT(*) = 1
        ) matched
        WHERE me.user_id = matched.user_id
          AND me.metaapi_account_id = matched.external_account_id
          AND me.connection_id IS NULL
        """
    )

    # Existing broker connections receive conservative policies. Linked demo
    # accounts become MANUAL-only; live/unknown accounts remain SIGNALS_ONLY.
    op.execute(
        """
        INSERT INTO trading_account_policies(
            policy_id,connection_id,user_id,policy_version,account_mode,
            execution_permission,status,currency,reset_timezone,
            max_risk_per_trade_pct,max_daily_loss_pct,max_weekly_loss_pct,max_total_drawdown_pct,
            max_open_positions,max_leverage,max_spread_bps,max_slippage_bps,
            min_confidence,min_expected_rr,safety_buffer_pct,
            allowed_instruments,allowed_asset_classes,allowed_strategies,trading_windows,
            news_trading_allowed,weekend_holding_allowed,
            external_rules,created_at,updated_at
        )
        SELECT
            gen_random_uuid()::text,
            bc.connection_id,
            bc.user_id,
            1,
            CASE
                WHEN UPPER(COALESCE(bc.meta->>'account_classification','')) = 'PROP' THEN 'PROP'
                WHEN LOWER(COALESCE(bc.environment,'')) = 'demo' THEN 'DEMO'
                WHEN LOWER(COALESCE(bc.environment,'')) = 'live' THEN 'LIVE_PERSONAL'
                ELSE 'DEMO'
            END,
            CASE
                WHEN LOWER(COALESCE(bc.environment,'')) = 'demo'
                     AND bc.execution_enabled IS TRUE THEN 'MANUAL'
                ELSE 'SIGNALS_ONLY'
            END,
            'configured',
            'USD',
            'UTC',
            0.005,
            0.04,
            0.08,
            0.08,
            3,
            1,
            50,
            25,
            0,
            0,
            0,
            '[]'::json,
            '[]'::json,
            '[]'::json,
            '[]'::json,
            TRUE,
            TRUE,
            '{}'::json,
            NOW(),
            NOW()
        FROM broker_connections bc
        ON CONFLICT(connection_id) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO broker_reconciliation_state(
            connection_id,user_id,status,last_reconciled_at,updated_at
        )
        SELECT
            connection_id,
            user_id,
            CASE
                WHEN last_health_at IS NOT NULL AND status IN ('linked','ready','verified')
                THEN 'RECONCILING'
                ELSE 'UNKNOWN'
            END,
            NULL,
            NOW()
        FROM broker_connections
        ON CONFLICT(connection_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_mt5_executions_connection_status", table_name="mt5_executions")
    op.drop_column("mt5_executions", "connection_id")
    op.drop_index("ix_broker_executions_connection_status", table_name="broker_executions")
    op.drop_column("broker_executions", "connection_id")
    op.drop_index("ix_broker_execution_decision_signal_user", table_name="broker_execution_decisions")
    op.drop_index("ix_broker_execution_decision_account_created", table_name="broker_execution_decisions")
    op.drop_table("broker_execution_decisions")
    op.drop_index("ix_broker_reconciliation_user_status", table_name="broker_reconciliation_state")
    op.drop_table("broker_reconciliation_state")
    op.drop_index("ix_trading_account_policy_user_mode", table_name="trading_account_policies")
    op.drop_table("trading_account_policies")
