"""init tables

Revision ID: 0001_init
Revises: 
Create Date: 2026-01-01

"""

from alembic import op
import sqlalchemy as sa


revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("telegram_user_id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_telegram_user_id", "users", ["telegram_user_id"], unique=True)

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tier", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("paystack_reference", sa.String(length=128), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_tier", "subscriptions", ["tier"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_unique_constraint("uq_subscriptions_paystack_reference", "subscriptions", ["paystack_reference"])

    op.create_table(
        "signals",
        sa.Column("signal_id", sa.String(length=36), primary_key=True),
        sa.Column("asset", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("entry", sa.Float(), nullable=False),
        sa.Column("stop_loss", sa.Float(), nullable=False),
        sa.Column("take_profit", sa.Text(), nullable=False),
        sa.Column("rr_estimate", sa.Float(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("regime", sa.String(length=32), nullable=True),
        sa.Column("strategy_name", sa.String(length=64), nullable=False),
        sa.Column("strategy_group", sa.String(length=32), nullable=False),
        sa.Column("strength", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_signals_asset", "signals", ["asset"])
    op.create_index("ix_signals_timeframe", "signals", ["timeframe"])
    op.create_index("ix_signals_direction", "signals", ["direction"])
    op.create_index("ix_signals_score", "signals", ["score"])

    op.create_table(
        "outcomes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("signal_id", sa.String(length=36), sa.ForeignKey("signals.signal_id"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("r_multiple", sa.Float(), nullable=True),
        sa.Column("percent", sa.Float(), nullable=True),
        sa.Column("opened_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False),
    )
    op.create_index("ix_outcomes_signal_id", "outcomes", ["signal_id"])
    op.create_index("ix_outcomes_status", "outcomes", ["status"])

    op.create_table(
        "strategy_stats",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("strategy_name", sa.String(length=64), nullable=False),
        sa.Column("strategy_group", sa.String(length=32), nullable=False),
        sa.Column("trades", sa.Integer(), nullable=False),
        sa.Column("win_rate", sa.Float(), nullable=False),
        sa.Column("avg_r", sa.Float(), nullable=False),
        sa.Column("ewma_weight", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_strategy_stats_strategy_name", "strategy_stats", ["strategy_name"])
    op.create_index("ix_strategy_stats_strategy_group", "strategy_stats", ["strategy_group"])

    op.create_table(
        "admin_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_telegram_user_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_admin_events_event_type", "admin_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_admin_events_event_type", table_name="admin_events")
    op.drop_table("admin_events")

    op.drop_index("ix_strategy_stats_strategy_group", table_name="strategy_stats")
    op.drop_index("ix_strategy_stats_strategy_name", table_name="strategy_stats")
    op.drop_table("strategy_stats")

    op.drop_index("ix_outcomes_status", table_name="outcomes")
    op.drop_index("ix_outcomes_signal_id", table_name="outcomes")
    op.drop_table("outcomes")

    op.drop_index("ix_signals_score", table_name="signals")
    op.drop_index("ix_signals_direction", table_name="signals")
    op.drop_index("ix_signals_timeframe", table_name="signals")
    op.drop_index("ix_signals_asset", table_name="signals")
    op.drop_table("signals")

    op.drop_constraint("uq_subscriptions_paystack_reference", "subscriptions", type_="unique")
    op.drop_index("ix_subscriptions_status", table_name="subscriptions")
    op.drop_index("ix_subscriptions_tier", table_name="subscriptions")
    op.drop_index("ix_subscriptions_user_id", table_name="subscriptions")
    op.drop_table("subscriptions")

    op.drop_index("ix_users_telegram_user_id", table_name="users")
    op.drop_table("users")
