from sqlalchemy.engine import make_url

from db.database_urls import normalize_sync_postgres_url


def test_railway_postgres_alias_uses_psycopg2_driver():
    url = normalize_sync_postgres_url(
        "postgres://user:password@postgres.railway.internal:5432/railway"
    )
    assert url == (
        "postgresql+psycopg2://user:password@"
        "postgres.railway.internal:5432/railway"
    )
    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql"
    assert parsed.get_driver_name() == "psycopg2"


def test_async_runtime_url_is_converted_for_sync_migrations():
    assert normalize_sync_postgres_url(
        "postgresql+asyncpg://user:password@localhost/db"
    ) == "postgresql+psycopg2://user:password@localhost/db"


def test_plain_postgresql_url_is_made_explicit():
    assert normalize_sync_postgres_url(
        "postgresql://user:password@localhost/db?sslmode=require"
    ) == (
        "postgresql+psycopg2://user:password@localhost/db?sslmode=require"
    )


def test_quoted_railway_value_is_unwrapped():
    assert normalize_sync_postgres_url(
        '"postgres://user:password@localhost/db"'
    ) == "postgresql+psycopg2://user:password@localhost/db"


def test_non_postgres_url_is_preserved():
    assert normalize_sync_postgres_url("sqlite:///local.db") == "sqlite:///local.db"
