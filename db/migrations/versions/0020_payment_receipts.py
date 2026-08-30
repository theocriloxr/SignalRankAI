"""Add and reconcile idempotent confirmed-payment receipts.

Revision ID: 0020_payment_receipts
Revises: 0019_user_timezone_privacy

This migration is intentionally tolerant of legacy environments where
``Base.metadata.create_all()`` or an older bootstrap path created the
``payment_receipts`` table before Alembic reached this revision.  It never
deletes receipt rows.  Duplicate legacy identities are retained, marked as
``duplicate`` and assigned deterministic archival keys before the canonical
unique indexes are installed.
"""
from __future__ import annotations

import logging

from alembic import op

revision = "0020_payment_receipts"
down_revision = "0019_user_timezone_privacy"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    # Serialise reconciliation across overlapping Railway pre-deploy attempts.
    op.execute(
        "SELECT pg_advisory_xact_lock(hashtext('signalrank:payment_receipts_schema'))"
    )

    # CREATE TABLE IF NOT EXISTS handles clean databases.  The ALTER statements
    # below repair tables that were created by historical bootstrap code.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS payment_receipts (
            id SERIAL PRIMARY KEY,
            receipt_number VARCHAR(64) NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(id),
            provider VARCHAR(32) NOT NULL DEFAULT 'paystack',
            payment_reference VARCHAR(128) NOT NULL,
            plan VARCHAR(64) NOT NULL,
            amount DOUBLE PRECISION NOT NULL,
            currency VARCHAR(8) NOT NULL DEFAULT 'NGN',
            status VARCHAR(16) NOT NULL DEFAULT 'paid',
            payment_date TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            subscription_start TIMESTAMP WITHOUT TIME ZONE,
            subscription_end TIMESTAMP WITHOUT TIME ZONE,
            text_body TEXT NOT NULL DEFAULT '',
            html_body TEXT,
            meta JSON NOT NULL DEFAULT '{}'::json
        )
        """
    )

    # Additive drift repair.  Columns with no safe historical derivation are
    # initially nullable; the guarded NOT NULL block below tightens them only
    # when the existing data permits it.
    op.execute("ALTER TABLE payment_receipts ADD COLUMN IF NOT EXISTS receipt_number VARCHAR(64)")
    op.execute("ALTER TABLE payment_receipts ADD COLUMN IF NOT EXISTS user_id INTEGER")
    op.execute("ALTER TABLE payment_receipts ADD COLUMN IF NOT EXISTS provider VARCHAR(32) DEFAULT 'paystack'")
    op.execute("ALTER TABLE payment_receipts ADD COLUMN IF NOT EXISTS payment_reference VARCHAR(128)")
    op.execute("ALTER TABLE payment_receipts ADD COLUMN IF NOT EXISTS plan VARCHAR(64)")
    op.execute("ALTER TABLE payment_receipts ADD COLUMN IF NOT EXISTS amount DOUBLE PRECISION")
    op.execute("ALTER TABLE payment_receipts ADD COLUMN IF NOT EXISTS currency VARCHAR(8) DEFAULT 'NGN'")
    op.execute("ALTER TABLE payment_receipts ADD COLUMN IF NOT EXISTS status VARCHAR(16) DEFAULT 'paid'")
    op.execute("ALTER TABLE payment_receipts ADD COLUMN IF NOT EXISTS payment_date TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()")
    op.execute("ALTER TABLE payment_receipts ADD COLUMN IF NOT EXISTS subscription_start TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE payment_receipts ADD COLUMN IF NOT EXISTS subscription_end TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE payment_receipts ADD COLUMN IF NOT EXISTS text_body TEXT DEFAULT ''")
    op.execute("ALTER TABLE payment_receipts ADD COLUMN IF NOT EXISTS html_body TEXT")
    op.execute("ALTER TABLE payment_receipts ADD COLUMN IF NOT EXISTS meta JSON DEFAULT '{}'::json")

    op.execute("UPDATE payment_receipts SET provider='paystack' WHERE provider IS NULL OR BTRIM(provider)='' ")
    op.execute("UPDATE payment_receipts SET currency='NGN' WHERE currency IS NULL OR BTRIM(currency)='' ")
    op.execute("UPDATE payment_receipts SET status='paid' WHERE status IS NULL OR BTRIM(status)='' ")
    op.execute("UPDATE payment_receipts SET payment_date=NOW() WHERE payment_date IS NULL")
    op.execute("UPDATE payment_receipts SET text_body='' WHERE text_body IS NULL")
    op.execute("UPDATE payment_receipts SET meta='{}'::json WHERE meta IS NULL")

    # Audit and preserve duplicate receipt numbers before assigning deterministic
    # archival values.  The original identifier remains in admin_events.
    op.execute(
        """
        WITH ranked AS (
            SELECT id, receipt_number,
                   ROW_NUMBER() OVER (PARTITION BY receipt_number ORDER BY id) AS rn,
                   FIRST_VALUE(id) OVER (PARTITION BY receipt_number ORDER BY id) AS canonical_id
            FROM payment_receipts
            WHERE receipt_number IS NOT NULL
        ), duplicates AS (
            SELECT * FROM ranked WHERE rn > 1
        )
        INSERT INTO admin_events(event_type, actor_telegram_user_id, details, created_at)
        SELECT 'migration_payment_receipt_dedupe', NULL,
               json_build_object(
                   'revision', '0020_payment_receipts',
                   'field', 'receipt_number',
                   'row_id', id,
                   'canonical_row_id', canonical_id,
                   'original_value', receipt_number,
                   'action', 'assigned_archival_unique_key',
                   'rows_deleted', 0
               ), NOW()
        FROM duplicates
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id, receipt_number,
                   ROW_NUMBER() OVER (PARTITION BY receipt_number ORDER BY id) AS rn
            FROM payment_receipts
            WHERE receipt_number IS NOT NULL
        )
        UPDATE payment_receipts p
        SET receipt_number = LEFT(p.receipt_number, 43) || '-legacy-' || p.id::text,
            status = 'duplicate'
        FROM ranked r
        WHERE p.id = r.id AND r.rn > 1
        """
    )

    # Apply the same non-destructive reconciliation to replayed provider payment
    # references.  This keeps one canonical row for entitlement/idempotency and
    # preserves every duplicate financial record for audit.
    op.execute(
        """
        WITH ranked AS (
            SELECT id, provider, payment_reference,
                   ROW_NUMBER() OVER (
                       PARTITION BY provider, payment_reference ORDER BY id
                   ) AS rn,
                   FIRST_VALUE(id) OVER (
                       PARTITION BY provider, payment_reference ORDER BY id
                   ) AS canonical_id
            FROM payment_receipts
            WHERE provider IS NOT NULL AND payment_reference IS NOT NULL
        ), duplicates AS (
            SELECT * FROM ranked WHERE rn > 1
        )
        INSERT INTO admin_events(event_type, actor_telegram_user_id, details, created_at)
        SELECT 'migration_payment_receipt_dedupe', NULL,
               json_build_object(
                   'revision', '0020_payment_receipts',
                   'field', 'provider_payment_reference',
                   'row_id', id,
                   'canonical_row_id', canonical_id,
                   'provider', provider,
                   'original_value', payment_reference,
                   'action', 'assigned_archival_unique_key',
                   'rows_deleted', 0
               ), NOW()
        FROM duplicates
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id, provider, payment_reference,
                   ROW_NUMBER() OVER (
                       PARTITION BY provider, payment_reference ORDER BY id
                   ) AS rn
            FROM payment_receipts
            WHERE provider IS NOT NULL AND payment_reference IS NOT NULL
        )
        UPDATE payment_receipts p
        SET payment_reference = LEFT(p.payment_reference, 99) || '#legacy-' || p.id::text,
            status = 'duplicate'
        FROM ranked r
        WHERE p.id = r.id AND r.rn > 1
        """
    )

    # A pre-existing table can contain incomplete bootstrap rows.  Do not invent
    # financial/user identity.  Abort with a precise diagnosis instead of
    # installing misleading constraints.
    op.execute(
        """
        DO $$
        DECLARE invalid_count bigint;
        BEGIN
            SELECT COUNT(*) INTO invalid_count
            FROM payment_receipts
            WHERE receipt_number IS NULL
               OR user_id IS NULL
               OR payment_reference IS NULL
               OR plan IS NULL
               OR amount IS NULL;
            IF invalid_count > 0 THEN
                RAISE EXCEPTION USING
                    MESSAGE = format(
                        'payment_receipts contains %s incomplete legacy row(s); run the receipt repair diagnostic before retrying migration',
                        invalid_count
                    ),
                    ERRCODE = '23502';
            END IF;
        END $$
        """
    )

    # Tighten the canonical contract only after data has been validated.
    for column in (
        "receipt_number", "user_id", "provider", "payment_reference", "plan",
        "amount", "currency", "status", "payment_date", "text_body", "meta",
    ):
        op.execute(f"ALTER TABLE payment_receipts ALTER COLUMN {column} SET NOT NULL")

    # Add the user FK only when an equivalent FK is absent.  NOT VALID avoids a
    # long table lock; validation still checks all rows before deployment ends.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_attribute a
                  ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                WHERE c.conrelid = 'payment_receipts'::regclass
                  AND c.contype = 'f'
                  AND a.attname = 'user_id'
            ) THEN
                ALTER TABLE payment_receipts
                    ADD CONSTRAINT fk_payment_receipts_user_id
                    FOREIGN KEY (user_id) REFERENCES users(id) NOT VALID;
                ALTER TABLE payment_receipts
                    VALIDATE CONSTRAINT fk_payment_receipts_user_id;
            END IF;
        END $$
        """
    )

    # Named unique indexes satisfy the idempotency contract regardless of
    # whether the legacy table originally used constraints or indexes.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_receipts_number "
        "ON payment_receipts(receipt_number)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_receipt_provider_reference "
        "ON payment_receipts(provider, payment_reference)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_payment_receipts_user_id "
        "ON payment_receipts(user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_payment_receipts_receipt_number "
        "ON payment_receipts(receipt_number)"
    )

    logger.warning(
        "payment_receipts schema reconciled idempotently; historical rows retained."
    )


def downgrade() -> None:
    # Receipt/payment evidence is financial audit data.  A downgrade must not
    # destroy it.  Only indexes introduced by this revision are removed.
    op.execute("DROP INDEX IF EXISTS ix_payment_receipts_receipt_number")
    op.execute("DROP INDEX IF EXISTS ix_payment_receipts_user_id")
    op.execute("DROP INDEX IF EXISTS uq_payment_receipt_provider_reference")
    op.execute("DROP INDEX IF EXISTS uq_payment_receipts_number")
