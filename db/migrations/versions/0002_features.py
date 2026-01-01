"""features

Revision ID: 0002_features
Revises: 0001_init
Create Date: 2026-01-01

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002_features"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add fingerprint column to signals
    op.add_column("signals", sa.Column("fingerprint", sa.String(length=128), nullable=True))
    op.create_index("ix_signals_fingerprint", "signals", ["fingerprint"], unique=False)

    # Alert preferences
    op.create_table(
        "alert_prefs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tp_sl_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("quiet_start_hour", sa.Integer(), nullable=True),
        sa.Column("quiet_end_hour", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_alert_prefs_user_id", "alert_prefs", ["user_id"], unique=True)

    # Referral tables
    op.create_table(
        "referral_codes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("referrer_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_referral_codes_code", "referral_codes", ["code"], unique=True)
    op.create_index(
        "ix_referral_codes_referrer_user_id",
        "referral_codes",
        ["referrer_user_id"],
        unique=False,
    )

    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("referred_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("referrer_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_referrals_referred_user_id", "referrals", ["referred_user_id"], unique=True)
    op.create_index("ix_referrals_referrer_user_id", "referrals", ["referrer_user_id"], unique=False)

    op.create_table(
        "referral_rewards",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("referrer_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("referred_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reward_type", sa.String(length=64), nullable=False),
        sa.Column("reward_value", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_referral_rewards_referrer_user_id",
        "referral_rewards",
        ["referrer_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_referral_rewards_reward_type",
        "referral_rewards",
        ["reward_type"],
        unique=False,
    )

    # Free signal delayed queue
    op.create_table(
        "free_signal_queue",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("signal_id", sa.String(length=36), sa.ForeignKey("signals.signal_id"), nullable=False),
        sa.Column("asset", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("queued_at", sa.DateTime(), nullable=False),
        sa.Column("deliver_after", sa.DateTime(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'queued'")),
    )
    op.create_index("ix_free_signal_queue_user_id", "free_signal_queue", ["user_id"], unique=False)
    op.create_index("ix_free_signal_queue_date", "free_signal_queue", ["date"], unique=False)
    op.create_index("ix_free_signal_queue_deliver_after", "free_signal_queue", ["deliver_after"], unique=False)
    op.create_index("ix_free_signal_queue_status", "free_signal_queue", ["status"], unique=False)

    # Signal deliveries (for /signals daily history + dedup per user)
    op.create_table(
        "signal_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("signal_id", sa.String(length=36), sa.ForeignKey("signals.signal_id"), nullable=False),
        sa.Column("tier_at_send", sa.String(length=16), nullable=False, server_default=sa.text("'free'")),
        sa.Column("delivered_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "signal_id", name="uq_signal_delivery_user_signal"),
    )
    op.create_index("ix_signal_deliveries_user_id", "signal_deliveries", ["user_id"], unique=False)
    op.create_index("ix_signal_deliveries_signal_id", "signal_deliveries", ["signal_id"], unique=False)
    op.create_index("ix_signal_deliveries_delivered_at", "signal_deliveries", ["delivered_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_signal_deliveries_delivered_at", table_name="signal_deliveries")
    op.drop_index("ix_signal_deliveries_signal_id", table_name="signal_deliveries")
    op.drop_index("ix_signal_deliveries_user_id", table_name="signal_deliveries")
    op.drop_table("signal_deliveries")

    op.drop_index("ix_free_signal_queue_status", table_name="free_signal_queue")
    op.drop_index("ix_free_signal_queue_deliver_after", table_name="free_signal_queue")
    op.drop_index("ix_free_signal_queue_date", table_name="free_signal_queue")
    op.drop_index("ix_free_signal_queue_user_id", table_name="free_signal_queue")
    op.drop_table("free_signal_queue")

    op.drop_index("ix_referral_rewards_reward_type", table_name="referral_rewards")
    op.drop_index("ix_referral_rewards_referrer_user_id", table_name="referral_rewards")
    op.drop_table("referral_rewards")

    op.drop_index("ix_referrals_referrer_user_id", table_name="referrals")
    op.drop_index("ix_referrals_referred_user_id", table_name="referrals")
    op.drop_table("referrals")

    op.drop_index("ix_referral_codes_referrer_user_id", table_name="referral_codes")
    op.drop_index("ix_referral_codes_code", table_name="referral_codes")
    op.drop_table("referral_codes")

    op.drop_index("ix_alert_prefs_user_id", table_name="alert_prefs")
    op.drop_table("alert_prefs")

    op.drop_index("ix_signals_fingerprint", table_name="signals")
    op.drop_column("signals", "fingerprint")
