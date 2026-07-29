"""launch-grade per-user paper trading

Revision ID: 0027_launch_paper_trading
Revises: 0026_adaptive_operational_hotfix
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0027_launch_paper_trading"
down_revision = "0026_adaptive_operational_hotfix"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "paper_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("starting_balance", sa.Float(), nullable=False, server_default="10000"),
        sa.Column("cash_balance", sa.Float(), nullable=False, server_default="10000"),
        sa.Column("realized_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("auto_trade_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("risk_pct", sa.Float(), nullable=False, server_default="1"),
        sa.Column("max_open_positions", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("min_signal_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("spread_bps", sa.Float(), nullable=False, server_default="2"),
        sa.Column("slippage_bps", sa.Float(), nullable=False, server_default="2"),
        sa.Column("fee_bps", sa.Float(), nullable=False, server_default="5"),
        sa.Column("target_mode", sa.String(length=8), nullable=False, server_default="TP1"),
        sa.Column("allowed_directions", sa.String(length=16), nullable=False, server_default="both"),
        sa.Column("allowed_asset_classes", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("user_id", name="uq_paper_accounts_user_id"),
    )
    op.create_index("ix_paper_accounts_user_id", "paper_accounts", ["user_id"], unique=True)
    op.create_index("ix_paper_accounts_status", "paper_accounts", ["status"])
    op.create_index("ix_paper_accounts_auto_trade", "paper_accounts", ["auto_trade_enabled", "status"])

    op.create_table(
        "paper_positions",
        sa.Column("position_id", sa.String(length=36), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("paper_accounts.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("signal_id", sa.String(length=36), sa.ForeignKey("signals.signal_id"), nullable=False),
        sa.Column("delivery_id", sa.Integer(), sa.ForeignKey("signal_deliveries.id")),
        sa.Column("asset", sa.String(length=32), nullable=False),
        sa.Column("asset_class", sa.String(length=16)),
        sa.Column("timeframe", sa.String(length=8)),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("signal_entry", sa.Float(), nullable=False),
        sa.Column("fill_entry", sa.Float(), nullable=False),
        sa.Column("current_price", sa.Float(), nullable=False),
        sa.Column("stop_loss", sa.Float(), nullable=False),
        sa.Column("take_profits", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("target_price", sa.Float()),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("notional", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reserved_cash", sa.Float(), nullable=False, server_default="0"),
        sa.Column("entry_fee", sa.Float(), nullable=False, server_default="0"),
        sa.Column("exit_fee", sa.Float(), nullable=False, server_default="0"),
        sa.Column("unrealized_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("realized_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("r_multiple", sa.Float()),
        sa.Column("opened_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("closed_at", sa.DateTime()),
        sa.Column("exit_reason", sa.String(length=64)),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="delivered_signal"),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("user_id", "signal_id", name="uq_paper_position_user_signal"),
    )
    for name, cols in (
        ("ix_paper_positions_account_id", ["account_id"]),
        ("ix_paper_positions_user_id", ["user_id"]),
        ("ix_paper_positions_signal_id", ["signal_id"]),
        ("ix_paper_positions_delivery_id", ["delivery_id"]),
        ("ix_paper_positions_asset", ["asset"]),
        ("ix_paper_positions_status", ["status"]),
        ("ix_paper_positions_opened_at", ["opened_at"]),
        ("ix_paper_positions_closed_at", ["closed_at"]),
    ):
        op.create_index(name, "paper_positions", cols)
    op.create_index("ix_paper_positions_open_scan", "paper_positions", ["status", "asset", "updated_at"])

    op.create_table(
        "paper_ledger_entries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("paper_accounts.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("position_id", sa.String(length=36)),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("balance_after", sa.Float(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    for name, cols in (
        ("ix_paper_ledger_account_id", ["account_id"]),
        ("ix_paper_ledger_user_id", ["user_id"]),
        ("ix_paper_ledger_position_id", ["position_id"]),
        ("ix_paper_ledger_entry_type", ["entry_type"]),
        ("ix_paper_ledger_created_at", ["created_at"]),
    ):
        op.create_index(name, "paper_ledger_entries", cols)


def downgrade():
    op.drop_table("paper_ledger_entries")
    op.drop_table("paper_positions")
    op.drop_table("paper_accounts")
