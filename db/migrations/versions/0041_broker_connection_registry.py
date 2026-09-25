"""provider-neutral broker connection registry

Revision ID: 0041_broker_connection_registry
Revises: 0040_cross_channel_paper_receipts
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041_broker_connection_registry"
down_revision = "0040_cross_channel_paper_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broker_connections",
        sa.Column("connection_id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("connector", sa.String(length=32), nullable=False),
        sa.Column("broker_name", sa.String(length=128), nullable=True),
        sa.Column("account_label", sa.String(length=128), nullable=True),
        sa.Column("account_ref", sa.String(length=128), nullable=True),
        sa.Column("external_account_id", sa.String(length=128), nullable=True),
        sa.Column("environment", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("auth_mode", sa.String(length=32), nullable=False, server_default="existing"),
        sa.Column("secret_encrypted", sa.Text(), nullable=True),
        sa.Column("server", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("permissions", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("capabilities", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("execution_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("last_health_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("last_error_message", sa.String(length=512), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index(
        "ix_broker_connections_user_status",
        "broker_connections",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_broker_connections_user_platform",
        "broker_connections",
        ["user_id", "platform"],
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_broker_connections_user_platform_account
        ON broker_connections(user_id,platform,account_ref)
        WHERE account_ref IS NOT NULL
        """
    )

    # Preserve the mature MT5 credential store as the secret source while
    # backfilling provider-neutral discovery/status rows. No password is copied.
    op.execute(
        """
        INSERT INTO broker_connections(
            connection_id,user_id,platform,connector,broker_name,account_label,
            account_ref,external_account_id,environment,auth_mode,server,status,
            permissions,capabilities,execution_enabled,is_default,verified_at,
            last_health_at,meta,created_at,updated_at
        )
        SELECT
            'legacy-mt5-' || c.user_id::text,
            c.user_id,
            'mt5',
            'metaapi',
            NULL,
            'MetaTrader 5',
            c.mt5_login,
            c.metaapi_account_id,
            CASE
                WHEN LOWER(COALESCE(c.server,'')) LIKE '%demo%' THEN 'demo'
                WHEN LOWER(COALESCE(c.server,'')) LIKE '%live%' THEN 'live'
                ELSE 'unknown'
            END,
            'legacy_encrypted_password',
            c.server,
            CASE WHEN c.metaapi_account_id IS NOT NULL THEN 'linked' ELSE 'credentials_saved' END,
            '{"trade": true, "read": true}'::json,
            '{"market_data": true, "orders": true, "positions": true, "hard_stop": true}'::json,
            FALSE,
            TRUE,
            CASE WHEN c.metaapi_account_id IS NOT NULL THEN COALESCE(c.updated_at,c.created_at,NOW()) ELSE NULL END,
            NULL,
            '{"credential_source": "mt5_credentials"}'::json,
            COALESCE(c.created_at,NOW()),
            COALESCE(c.updated_at,c.created_at,NOW())
        FROM mt5_credentials c
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_broker_connections_user_platform", table_name="broker_connections")
    op.drop_index("ix_broker_connections_user_status", table_name="broker_connections")
    op.drop_table("broker_connections")
