from pathlib import Path


MIGRATION = Path("db/migrations/versions/0020_payment_receipts.py")


def _source() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_payment_receipt_migration_tolerates_existing_table() -> None:
    source = _source()
    assert "CREATE TABLE IF NOT EXISTS payment_receipts" in source
    assert "ADD COLUMN IF NOT EXISTS" in source
    assert "pg_advisory_xact_lock" in source


def test_payment_receipt_migration_preserves_and_audits_duplicates() -> None:
    source = _source()
    assert "migration_payment_receipt_dedupe" in source
    assert "rows_deleted', 0" in source
    assert "status = 'duplicate'" in source
    assert "DROP TABLE" not in source.upper()


def test_payment_receipt_migration_enforces_canonical_idempotency_indexes() -> None:
    source = _source()
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_receipts_number" in source
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_receipt_provider_reference" in source
    assert "CREATE INDEX IF NOT EXISTS ix_payment_receipts_user_id" in source


def test_payment_receipt_migration_fails_closed_for_incomplete_financial_rows() -> None:
    source = _source()
    assert "incomplete legacy row(s)" in source
    assert "ERUsing" not in source
    assert "ERRCODE = '23502'" in source
