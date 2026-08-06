from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_start_is_fail_closed_on_schema_mismatch():
    source = (ROOT / "start.sh").read_text(encoding="utf-8")
    assert "scripts/assert_database_schema.py" in source
    assert "Database schema admission failed" in source
    assert "exit 78" in source
    assert "DATABASE_SCHEMA_GATE_ENABLED" in source


def test_schema_gate_requires_unified_platform_objects():
    source = (ROOT / "scripts" / "assert_database_schema.py").read_text(encoding="utf-8")
    for required in (
        "subscription_products",
        "instruments",
        "webhook_deliveries",
        "auth_identities",
        "user_sessions",
        "users_public_user_id",
    ):
        assert required in source
    assert "alembic_expected_head" in source
    assert "EXIT_SCHEMA_MISMATCH = 78" in source


def test_staging_migration_is_guarded_locked_and_verified():
    source = (ROOT / "scripts" / "staging_migrate_and_bootstrap.py").read_text(encoding="utf-8")
    assert "STAGING_MIGRATION_ACKNOWLEDGED" in source
    assert "pg_advisory_lock" in source
    assert "pg_advisory_unlock" in source
    assert "command.upgrade" in source
    assert "assert_database_schema.py" in source
    assert "tools.bootstrap_ecosystem" in source
    assert "production" in source and "staging-only" in source


def test_production_migration_lock_uses_direct_migration_database():
    source = (ROOT / "scripts" / "controlled_migrate.py").read_text(encoding="utf-8")
    database_url = source[source.index("def _database_url"):source.index("def migrate")]
    assert 'DATABASE_MIGRATION_URL' in database_url
    assert 'DATABASE_DIRECT_URL' in database_url
    assert 'normalize_sync_postgres_url' in database_url


def test_railway_completion_script_enforces_common_db_and_safe_flags():
    source = (ROOT / "scripts" / "railway_finish_staging.ps1").read_text(encoding="utf-8")
    assert '${{' in source and '.DATABASE_URL}}' in source
    for service in ("SignalRankAI", "striking-optimism", "bountiful-miracle"):
        assert service in source
    for safe_flag in (
        "REAL_EXECUTION_ENABLED=0",
        "AUTO_TRADE_ENABLED=0",
        "COPY_TRADE_ENABLED=0",
        "REAL_PAYOUTS_ENABLED=0",
        "PAYMENTS_PUBLIC_ENABLED=0",
    ):
        assert safe_flag in source
    assert "staging_migrate_and_bootstrap.py" in source
    assert "database_identity.py" in source
    assert "0038_account_security_product" in source
    assert "UndefinedTableError" in source
    assert "UndefinedColumnError" in source


def test_railway_completion_migrates_before_uploading_services():
    source = (ROOT / "scripts" / "railway_finish_staging.ps1").read_text(encoding="utf-8")
    migration = source.index('"python", "scripts/staging_migrate_and_bootstrap.py"')
    upload = source.index('"up", "-s", $service')
    assert migration < upload


def test_staging_shell_entrypoint_delegates_to_guarded_python_command():
    source = (ROOT / "scripts" / "staging_predeploy_v151.sh").read_text(encoding="utf-8")
    assert "STAGING_MIGRATION_ACKNOWLEDGED=1 is required" in source
    assert "staging_migrate_and_bootstrap.py" in source
    assert "alembic upgrade head" not in source
