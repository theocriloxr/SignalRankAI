"""Retire duplicate MT5 password persistence after canonical credential envelopes.

Revision ID: 0045_mt5_credential_retirement
Revises: 0044_broker_credential_envelope
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0045_mt5_credential_retirement"
down_revision = "0044_broker_credential_envelope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The legacy table remains as a compatibility metadata alias while callers
    # migrate to broker_connections. New code must not persist passwords here.
    op.alter_column(
        "mt5_credentials",
        "password_encrypted",
        existing_type=sa.String(length=512),
        nullable=True,
    )

    # Scrub duplicate legacy password ciphertext only when an equivalent
    # canonical MT5 MetaApi connection already has a versioned envelope.
    # No credential is decrypted by this migration.
    op.execute(
        """
        UPDATE mt5_credentials AS legacy
        SET password_encrypted = NULL,
            updated_at = NOW()
        WHERE legacy.password_encrypted IS NOT NULL
          AND BTRIM(legacy.password_encrypted) <> ''
          AND EXISTS (
              SELECT 1
              FROM broker_connections AS canonical
              WHERE canonical.user_id = legacy.user_id
                AND LOWER(COALESCE(canonical.platform, '')) = 'mt5'
                AND LOWER(COALESCE(canonical.connector, '')) = 'metaapi'
                AND canonical.credential_format = 'envelope_v1'
                AND canonical.secret_encrypted IS NOT NULL
                AND BTRIM(canonical.secret_encrypted) <> ''
          )
        """
    )


def downgrade() -> None:
    # A downgrade cannot reconstruct scrubbed passwords. Empty compatibility
    # placeholders keep the historical NOT NULL shape without inventing secrets.
    op.execute(
        """
        UPDATE mt5_credentials
        SET password_encrypted = ''
        WHERE password_encrypted IS NULL
        """
    )
    op.alter_column(
        "mt5_credentials",
        "password_encrypted",
        existing_type=sa.String(length=512),
        nullable=False,
    )
