"""Canonical signal identity and per-recipient monitoring reliability.

Revision ID: 0030_signal_monitoring_reliability
Revises: 0029_live_financial_ledger
Create Date: 2026-07-31
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0030_signal_monitoring_reliability"
down_revision = "0029_live_financial_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("display_id", sa.String(20), nullable=True))
    # Resolve the exceptionally rare first-12 collision deterministically; no
    # existing UUID or delivery relationship is rewritten.
    op.execute("""
        WITH candidates AS (
            SELECT signal_id, LEFT(LOWER(signal_id), 12) AS candidate,
                   COUNT(*) OVER (PARTITION BY LEFT(LOWER(signal_id), 12)) AS collisions
            FROM signals
        )
        UPDATE signals AS s
        SET display_id = CASE
            WHEN c.collisions = 1 THEN c.candidate
            ELSE c.candidate || '-' || LEFT(MD5(c.signal_id), 7)
        END
        FROM candidates AS c
        WHERE c.signal_id = s.signal_id AND s.display_id IS NULL
    """)
    op.alter_column("signals", "display_id", nullable=False)
    op.create_index("ux_signals_display_id", "signals", ["display_id"], unique=True)

    op.add_column("users", sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("is_suspended", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_users_is_blocked", "users", ["is_blocked"])
    op.create_index("ix_users_is_suspended", "users", ["is_suspended"])

    op.add_column("signal_lifecycles", sa.Column("highest_tp_hit", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("signal_lifecycles", sa.Column("terminal_event_type", sa.String(32), nullable=True))
    op.add_column("signal_lifecycles", sa.Column("terminal_event_id", sa.BigInteger(), nullable=True))
    op.add_column("signal_lifecycles", sa.Column("terminal_price", sa.Float(), nullable=True))
    op.add_column(
        "signal_lifecycles",
        sa.Column("terminal_evidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_foreign_key(
        "fk_signal_lifecycle_terminal_event",
        "signal_lifecycles", "signal_tracking_events",
        ["terminal_event_id"], ["id"],
    )
    op.execute("""
        UPDATE signal_lifecycles
        SET highest_tp_hit = CASE
            WHEN tp3_hit_at IS NOT NULL OR state = 'TP3_HIT' THEN 3
            WHEN tp2_hit_at IS NOT NULL OR state = 'TP2_HIT' THEN 2
            WHEN tp1_hit_at IS NOT NULL OR state = 'TP1_HIT' THEN 1
            ELSE 0 END
    """)

    op.create_table(
        "user_signal_monitoring",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("signal_id", sa.String(36), sa.ForeignKey("signals.signal_id"), nullable=False),
        sa.Column("delivery_id", sa.Integer(), sa.ForeignKey("signal_deliveries.id"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="auto_continue"),
        sa.Column("highest_notified_tp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stopped_at_stage", sa.Integer(), nullable=True),
        sa.Column("stopped_at", sa.DateTime(), nullable=True),
        sa.Column("continued_at", sa.DateTime(), nullable=True),
        sa.Column("access_revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("user_id", "signal_id", name="uq_user_signal_monitoring_user_signal"),
    )
    op.create_index("ix_user_signal_monitoring_user_id", "user_signal_monitoring", ["user_id"])
    op.create_index("ix_user_signal_monitoring_signal_id", "user_signal_monitoring", ["signal_id"])
    op.create_index("ix_user_signal_monitoring_status", "user_signal_monitoring", ["status"])
    op.execute("""
        INSERT INTO user_signal_monitoring(user_id, signal_id, delivery_id, status, created_at, updated_at)
        SELECT sd.user_id, sd.signal_id, sd.id, 'auto_continue',
               COALESCE(sd.delivery_confirmed_at, sd.delivered_at, NOW()), NOW()
        FROM signal_deliveries sd
        WHERE sd.sent_ok IS TRUE
          AND sd.telegram_chat_id IS NOT NULL
          AND sd.telegram_message_id IS NOT NULL
          AND LOWER(COALESCE(sd.delivery_state, '')) IN ('sent','confirmed','delivered','reconciled')
        ON CONFLICT (user_id, signal_id) DO NOTHING
    """)

    op.create_table(
        "user_signal_monitoring_actions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("monitoring_id", sa.BigInteger(), sa.ForeignKey("user_signal_monitoring.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("signal_id", sa.String(36), sa.ForeignKey("signals.signal_id"), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("idempotency_key", name="uq_user_signal_monitoring_action_key"),
    )
    op.create_index("ix_user_signal_monitoring_actions_monitoring_id", "user_signal_monitoring_actions", ["monitoring_id"])
    op.create_index("ix_user_signal_monitoring_actions_user_id", "user_signal_monitoring_actions", ["user_id"])
    op.create_index("ix_user_signal_monitoring_actions_signal_id", "user_signal_monitoring_actions", ["signal_id"])

    op.add_column("signal_event_notifications", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("signal_event_notifications", sa.Column("last_attempt_at", sa.DateTime(), nullable=True))
    op.add_column("signal_event_notifications", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")))
    op.create_index(
        "ix_signal_event_notifications_claim",
        "signal_event_notifications", ["delivery_state", "last_attempt_at"],
    )

    # Stale Free rows are quarantined, never emitted in a burst after rollout.
    op.execute("""
        UPDATE free_signal_queue
        SET status = 'quarantined'
        WHERE status = 'queued' AND sent_at IS NULL
          AND deliver_after < NOW() - INTERVAL '24 hours'
    """)


def downgrade() -> None:
    op.drop_index("ix_signal_event_notifications_claim", table_name="signal_event_notifications")
    op.drop_column("signal_event_notifications", "updated_at")
    op.drop_column("signal_event_notifications", "last_attempt_at")
    op.drop_column("signal_event_notifications", "attempt_count")

    op.drop_table("user_signal_monitoring_actions")
    op.drop_table("user_signal_monitoring")

    op.drop_constraint("fk_signal_lifecycle_terminal_event", "signal_lifecycles", type_="foreignkey")
    for column in ("terminal_evidence", "terminal_price", "terminal_event_id", "terminal_event_type", "highest_tp_hit"):
        op.drop_column("signal_lifecycles", column)

    op.drop_index("ix_users_is_suspended", table_name="users")
    op.drop_index("ix_users_is_blocked", table_name="users")
    op.drop_column("users", "is_suspended")
    op.drop_column("users", "is_blocked")

    op.drop_index("ux_signals_display_id", table_name="signals")
    op.drop_column("signals", "display_id")
