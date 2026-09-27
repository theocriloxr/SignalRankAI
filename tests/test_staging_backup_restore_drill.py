from __future__ import annotations

from pathlib import Path


def test_restore_drill_is_staging_only_and_fail_closed() -> None:
    text = Path("scripts/staging_backup_restore_drill.py").read_text(encoding="utf-8")
    assert 'environment != "staging"' in text
    assert "STAGING_BACKUP_RESTORE_DRILL_ACK" in text
    assert "restore_drill_requires_flag_off" in text
    assert "source_database_mutation" in text
    assert '"source_database_mutation": False' in text


def test_restore_drill_uses_consistent_dump_isolated_database_and_cleanup() -> None:
    text = Path("scripts/staging_backup_restore_drill.py").read_text(encoding="utf-8")
    assert '"pg_dump"' in text
    assert '"--format=custom"' in text
    assert 'CREATE DATABASE "{target_db}"' in text
    assert '"pg_restore"' in text
    assert "restored_alembic_head_mismatch" in text
    assert "trg_trading_account_ledger_immutable" in text
    assert 'DROP DATABASE IF EXISTS "{target_db}" WITH (FORCE)' in text
    assert "dump_sha256" in text
    assert "dump_seconds" in text
    assert "restore_seconds" in text


def test_restore_drill_image_uses_postgresql_18_client() -> None:
    dockerfile = Path("Dockerfile.restore-drill").read_text(encoding="utf-8")
    assert "FROM postgres:18-alpine" in dockerfile
