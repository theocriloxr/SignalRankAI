import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import text

from tests.test_adaptive_worker_research_postgres import worker_database  # noqa: F401


@pytest.mark.asyncio
async def test_renewal_default_migration_preserves_existing_account_preferences(worker_database, monkeypatch):
    """The fixture owns a fresh localhost test database, never the configured app DB."""
    migration = importlib.import_module("db.migrations.versions.0055_user_renewal_default")
    async with worker_database() as session:
        await session.execute(text("ALTER TABLE users ALTER COLUMN auto_renew SET DEFAULT TRUE"))
        before = (await session.execute(text(
            "INSERT INTO users(telegram_user_id,created_at,updated_at) VALUES(987650901,NOW(),NOW()) RETURNING auto_renew"))).scalar_one()
        assert before is True

        def apply_upgrade(sync_session):
            operations = Operations(MigrationContext.configure(sync_session.connection()))
            monkeypatch.setattr(migration, "op", operations)
            migration.upgrade()

        await session.run_sync(apply_upgrade)
        after = (await session.execute(text(
            "INSERT INTO users(telegram_user_id,created_at,updated_at) VALUES(987650902,NOW(),NOW()) RETURNING auto_renew"))).scalar_one()
        assert after is False
        preserved = (await session.execute(text(
            "SELECT auto_renew FROM users WHERE telegram_user_id=987650901"))).scalar_one()
        assert preserved is True
