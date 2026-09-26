"""Versioned broker credential envelope metadata.

Revision ID: 0044_broker_credential_envelope
Revises: 0043_account_execution_policy
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0044_broker_credential_envelope"
down_revision = "0043_account_execution_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "broker_connections",
        sa.Column(
            "credential_format",
            sa.String(length=32),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "broker_connections",
        sa.Column(
            "credential_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "broker_connections",
        sa.Column("credential_key_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "broker_connections",
        sa.Column(
            "credential_revision",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "broker_connections",
        sa.Column("credential_rotated_at", sa.DateTime(), nullable=True),
    )

    # Existing values were already application-encrypted with ENCRYPTION_KEY,
    # but they are not context-bound/versioned envelopes. Mark them for lazy or
    # explicit rotation without decrypting them in a migration.
    op.execute(
        """
        UPDATE broker_connections
        SET credential_format = 'legacy_fernet',
            credential_version = 0,
            credential_revision = 0
        WHERE secret_encrypted IS NOT NULL
          AND BTRIM(secret_encrypted) <> ''
        """
    )

    op.create_check_constraint(
        "ck_broker_connections_credential_format",
        "broker_connections",
        "credential_format IN ('none','provider_managed','legacy_fernet','envelope_v1')",
    )
    op.create_check_constraint(
        "ck_broker_connections_credential_version",
        "broker_connections",
        "credential_version >= 0",
    )
    op.create_check_constraint(
        "ck_broker_connections_credential_revision",
        "broker_connections",
        "credential_revision >= 0",
    )
    op.create_index(
        "ix_broker_connections_credential_key_id",
        "broker_connections",
        ["credential_key_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_broker_connections_credential_key_id",
        table_name="broker_connections",
    )
    op.drop_constraint(
        "ck_broker_connections_credential_revision",
        "broker_connections",
        type_="check",
    )
    op.drop_constraint(
        "ck_broker_connections_credential_version",
        "broker_connections",
        type_="check",
    )
    op.drop_constraint(
        "ck_broker_connections_credential_format",
        "broker_connections",
        type_="check",
    )
    op.drop_column("broker_connections", "credential_rotated_at")
    op.drop_column("broker_connections", "credential_revision")
    op.drop_column("broker_connections", "credential_key_id")
    op.drop_column("broker_connections", "credential_version")
    op.drop_column("broker_connections", "credential_format")
