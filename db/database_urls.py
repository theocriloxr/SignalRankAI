"""Database URL normalisation helpers.

These helpers are intentionally dependency-light so they can be imported by
Alembic before the application runtime is initialised.
"""

from __future__ import annotations


def normalize_sync_postgres_url(raw: str) -> str:
    """Return a SQLAlchemy 2 compatible synchronous PostgreSQL URL.

    Railway commonly exposes ``postgres://`` URLs, while SQLAlchemy 2 expects
    the canonical ``postgresql`` dialect name.  The application runtime uses
    asyncpg, but Alembic runs synchronously and the project installs
    psycopg2-binary, so migration URLs are normalised to the explicit
    ``postgresql+psycopg2`` driver.

    Non-PostgreSQL URLs are returned unchanged to preserve local/test database
    support.
    """

    url = str(raw or "").strip()
    if len(url) >= 2 and url[0] == url[-1] and url[0] in {"'", '"'}:
        url = url[1:-1].strip()

    replacements = (
        ("postgresql+asyncpg://", "postgresql+psycopg2://"),
        ("postgresql+psycopg://", "postgresql+psycopg2://"),
        ("postgresql://", "postgresql+psycopg2://"),
        ("postgres://", "postgresql+psycopg2://"),
    )
    for source, target in replacements:
        if url.startswith(source):
            return url.replace(source, target, 1)
    return url


def normalize_psycopg2_dsn(raw: str) -> str:
    """Return a libpq/psycopg2 compatible PostgreSQL DSN URL.

    SQLAlchemy accepts driver-qualified URLs such as
    ``postgresql+psycopg2://``.  ``psycopg2.connect`` does not; it expects
    a normal PostgreSQL URI (or keyword DSN).  Keep this conversion separate
    from :func:`normalize_sync_postgres_url` so callers cannot accidentally
    feed a SQLAlchemy-only URL into libpq.
    """

    url = str(raw or "").strip()
    if len(url) >= 2 and url[0] == url[-1] and url[0] in {"'", '"'}:
        url = url[1:-1].strip()

    replacements = (
        ("postgresql+asyncpg://", "postgresql://"),
        ("postgresql+psycopg2://", "postgresql://"),
        ("postgresql+psycopg://", "postgresql://"),
        ("postgres://", "postgresql://"),
    )
    for source, target in replacements:
        if url.startswith(source):
            return url.replace(source, target, 1)
    return url
