#!/usr/bin/env python3
"""Backup-gated, advisory-locked Alembic migration for Railway pre-deploy.

This command mutates the database only after the release source and production
backup evidence are valid. It holds the SignalRankAI PostgreSQL advisory lock
for the complete Alembic upgrade and proves the deployed revision afterwards.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOCK_ID = 915_337_121
MAX_BACKUP_AGE = timedelta(hours=24)


def _value(name: str) -> str:
    return str(os.getenv(name) or "").strip().strip('"').strip("'")


def _truthy(name: str) -> bool:
    return _value(name).lower() in {"1", "true", "yes", "on"}


def _environment() -> str:
    return (_value("RAILWAY_ENVIRONMENT_NAME") or _value("RAILWAY_ENVIRONMENT") or _value("APP_ENV") or "dev").lower()


def _parse_utc(value: str) -> datetime | None:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if result.tzinfo is None:
        return None
    return result.astimezone(timezone.utc)


def _source_errors() -> list[str]:
    errors: list[str] = []
    railway = bool(_value("RAILWAY_SERVICE_NAME") or _value("RAILWAY_PROJECT_ID"))
    protected = railway or _environment() in {"production", "prod"} or _value("SIGNALRANK_ENV_PROFILE") in {
        "staging-certification", "production-advisory", "production-live-owner-canary"
    }
    if not protected:
        return errors

    from core.version import runtime_commit_matches_expected

    commit_ok, detail = runtime_commit_matches_expected()
    if not commit_ok:
        errors.append(detail)
    expected_branch = _value("EXPECTED_RELEASE_BRANCH")
    actual_branch = _value("RAILWAY_GIT_BRANCH") or _value("GIT_BRANCH")
    if not expected_branch:
        errors.append("EXPECTED_RELEASE_BRANCH is missing")
    elif actual_branch != expected_branch:
        errors.append(f"runtime branch {actual_branch or 'unknown'} does not match {expected_branch}")
    expected_service = _value("EXPECTED_RAILWAY_SERVICE")
    actual_service = _value("RAILWAY_SERVICE_NAME")
    if railway and not expected_service:
        errors.append("EXPECTED_RAILWAY_SERVICE is missing")
    elif railway and actual_service != expected_service:
        errors.append(f"Railway service {actual_service or 'unknown'} does not match {expected_service}")
    return errors


def _backup_errors() -> list[str]:
    if _environment() not in {"production", "prod"}:
        return []
    errors: list[str] = []
    backup_id = _value("PRODUCTION_DB_BACKUP_ID")
    created_at = _parse_utc(_value("PRODUCTION_DB_BACKUP_CREATED_AT"))
    now = datetime.now(timezone.utc)
    if not _truthy("PRODUCTION_DB_BACKUP_VERIFIED"):
        errors.append("PRODUCTION_DB_BACKUP_VERIFIED must be 1")
    if not backup_id:
        errors.append("PRODUCTION_DB_BACKUP_ID is missing")
    if created_at is None:
        errors.append("PRODUCTION_DB_BACKUP_CREATED_AT must be a timezone-aware ISO-8601 timestamp")
    elif created_at > now or now - created_at > MAX_BACKUP_AGE:
        errors.append("production database backup must be no more than 24 hours old")
    return errors


def _expected_head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(ROOT / "alembic.ini"))
    heads = tuple(ScriptDirectory.from_config(config).get_heads())
    if len(heads) != 1:
        raise RuntimeError(f"repository must have one Alembic head, found {heads}")
    return heads[0]


def _database_urls() -> tuple[str, str]:
    # The advisory lock, pre/post revision reads and Alembic itself must target
    # the exact same direct database.  Using DATABASE_URL for the lock while
    # Alembic uses DATABASE_MIGRATION_URL can migrate one database while
    # verifying another.
    from db.database_urls import normalize_psycopg2_dsn, normalize_sync_postgres_url

    raw = (
        _value("DATABASE_MIGRATION_URL")
        or _value("DATABASE_DIRECT_URL")
        or _value("DATABASE_URL")
    )
    if not raw:
        raise RuntimeError(
            "DATABASE_MIGRATION_URL/DATABASE_DIRECT_URL/DATABASE_URL is not configured"
        )
    return normalize_sync_postgres_url(raw), normalize_psycopg2_dsn(raw)


def migrate() -> dict[str, Any]:
    errors = _source_errors() + _backup_errors()
    if errors:
        raise RuntimeError("; ".join(errors))

    import psycopg2
    from alembic import command
    from alembic.config import Config

    expected = _expected_head()
    db_url, db_dsn = _database_urls()
    started_at = datetime.now(timezone.utc)
    with closing(psycopg2.connect(db_dsn, connect_timeout=10)) as connection:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version_num FROM alembic_version LIMIT 1")
                row = cursor.fetchone()
                before = str(row[0]) if row else None
            config = Config(str(ROOT / "alembic.ini"))
            config.set_main_option("sqlalchemy.url", db_url)
            command.upgrade(config, "head")
            with connection.cursor() as cursor:
                cursor.execute("SELECT version_num FROM alembic_version LIMIT 1")
                row = cursor.fetchone()
                after = str(row[0]) if row else None
            if after != expected:
                raise RuntimeError(f"migration verification failed: current={after} expected={expected}")
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))

    return {
        "status": "PASS",
        "evidence_type": "integration",
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "environment": _environment(),
        "release_commit": (_value("RAILWAY_GIT_COMMIT_SHA") or _value("GIT_COMMIT_SHA"))[:12],
        "backup_id": _value("PRODUCTION_DB_BACKUP_ID") or None,
        "alembic_before": before,
        "alembic_current": after,
        "alembic_expected_head": expected,
        "advisory_lock_id": LOCK_ID,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="/tmp/signalrank_migration_evidence.json")
    args = parser.parse_args()
    output = Path(args.output)
    try:
        payload = migrate()
        exit_code = 0
    except Exception as exc:
        payload = {
            "status": "BLOCKED",
            "evidence_type": "integration",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "environment": _environment(),
            "error": f"{type(exc).__name__}: {exc}",
        }
        exit_code = 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
