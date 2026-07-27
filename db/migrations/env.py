from __future__ import annotations

from pathlib import Path
import os
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(".env", override=False)
    load_dotenv(".env.local", override=True)
except Exception:
    pass
from config import config as app_config
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from db.models import Base
from db.database_urls import normalize_sync_postgres_url

# Alembic Config object
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_url() -> str:
    # Migrations should use a direct PostgreSQL connection when runtime traffic
    # is routed through PgBouncer transaction pooling.  Fall back to the runtime
    # URL for simple/direct-Postgres deployments.
    url = (
        os.getenv("DATABASE_MIGRATION_URL")
        or os.getenv("DATABASE_DIRECT_URL")
        or app_config.DATABASE_URL
    )
    if not url:
        raise RuntimeError(
            "DATABASE_MIGRATION_URL/DATABASE_DIRECT_URL/DATABASE_URL is not set"
        )
    # Railway commonly emits ``postgres://`` while SQLAlchemy 2 requires the
    # canonical ``postgresql`` dialect. Alembic is synchronous, so use the
    # explicitly installed psycopg2 driver for all PostgreSQL URL variants.
    return normalize_sync_postgres_url(url)


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
