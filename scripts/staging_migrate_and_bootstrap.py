#!/usr/bin/env python3
"""One-owner SignalRankAI staging migration, schema proof and ecosystem bootstrap.

The command is intentionally staging-only. It acquires the same PostgreSQL
advisory lock used by production migrations, upgrades to the repository's
single Alembic head, verifies the unified schema, seeds products/entitlements,
performs optional instrument discovery and records evidence.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOCK_ID = 915_337_121


def _value(name: str) -> str:
    return str(os.getenv(name) or "").strip().strip('"').strip("'")


def _truthy(name: str) -> bool:
    return _value(name).lower() in {"1", "true", "yes", "on"}


def _environment() -> str:
    return (
        _value("RAILWAY_ENVIRONMENT_NAME")
        or _value("RAILWAY_ENVIRONMENT")
        or _value("APP_ENV")
        or _value("ENVIRONMENT")
        or "dev"
    ).lower()


def _expected_head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(ROOT / "alembic.ini"))
    heads = tuple(ScriptDirectory.from_config(cfg).get_heads())
    if len(heads) != 1:
        raise RuntimeError(f"repository must have exactly one Alembic head; found {heads}")
    return str(heads[0])


def _migration_urls() -> tuple[str, str]:
    from db.database_urls import normalize_psycopg2_dsn, normalize_sync_postgres_url

    raw = (
        _value("DATABASE_MIGRATION_URL")
        or _value("DATABASE_DIRECT_URL")
        or _value("DATABASE_URL")
    )
    if not raw:
        raise RuntimeError("DATABASE_MIGRATION_URL/DATABASE_DIRECT_URL/DATABASE_URL is missing")
    return normalize_sync_postgres_url(raw), normalize_psycopg2_dsn(raw)


def _run(command: list[str], *, env: dict[str, str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    sys.stdout.write(completed.stdout)
    return {
        "command": command,
        "returncode": int(completed.returncode),
        "output_tail": completed.stdout[-8000:],
    }


def migrate_and_bootstrap(*, discover: bool, top: int, run_certification: bool) -> dict[str, Any]:
    environment = _environment()
    if environment in {"production", "prod"}:
        raise RuntimeError("this command is staging-only; use scripts/controlled_migrate.py for production")
    if environment not in {"staging", "stage", "preview", "development", "dev", "test"}:
        raise RuntimeError(f"unrecognized non-production environment: {environment}")
    if not _truthy("STAGING_MIGRATION_ACKNOWLEDGED"):
        raise RuntimeError("STAGING_MIGRATION_ACKNOWLEDGED=1 is required")

    from alembic import command
    from alembic.config import Config
    import psycopg2

    expected = _expected_head()
    configured_expected = _value("EXPECTED_ALEMBIC_HEAD")
    if configured_expected and configured_expected != expected:
        raise RuntimeError(
            f"EXPECTED_ALEMBIC_HEAD={configured_expected} does not match repository head {expected}"
        )

    migration_url, migration_dsn = _migration_urls()
    started_at = datetime.now(timezone.utc)
    before: str | None = None
    after: str | None = None

    with closing(psycopg2.connect(migration_dsn, connect_timeout=15)) as connection:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version_num FROM alembic_version LIMIT 1")
                row = cursor.fetchone()
                before = str(row[0]) if row else None

            cfg = Config(str(ROOT / "alembic.ini"))
            cfg.set_main_option("sqlalchemy.url", migration_url)
            migration_env = os.environ.copy()
            migration_env["DATABASE_MIGRATION_URL"] = migration_url
            previous = os.environ.get("DATABASE_MIGRATION_URL")
            os.environ["DATABASE_MIGRATION_URL"] = migration_url
            try:
                command.upgrade(cfg, "head")
            finally:
                if previous is None:
                    os.environ.pop("DATABASE_MIGRATION_URL", None)
                else:
                    os.environ["DATABASE_MIGRATION_URL"] = previous

            with connection.cursor() as cursor:
                cursor.execute("SELECT version_num FROM alembic_version LIMIT 1")
                row = cursor.fetchone()
                after = str(row[0]) if row else None
            if after != expected:
                raise RuntimeError(f"migration verification failed: current={after} expected={expected}")
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))

    runtime_env = os.environ.copy()
    # Bootstrap must target the exact database just migrated, not a stale runtime URL.
    runtime_env["DATABASE_URL"] = migration_dsn
    runtime_env["DATABASE_MIGRATION_URL"] = migration_url

    schema = _run(
        [sys.executable, str(ROOT / "scripts" / "assert_database_schema.py"), "--json"],
        env=runtime_env,
    )
    if schema["returncode"] != 0:
        raise RuntimeError("post-migration schema admission check failed")

    bootstrap_command = [sys.executable, "-m", "tools.bootstrap_ecosystem"]
    if discover:
        bootstrap_command.append("--discover")
    bootstrap_command.extend(["--top", str(max(1, top))])
    bootstrap = _run(bootstrap_command, env=runtime_env)
    if bootstrap["returncode"] != 0:
        raise RuntimeError("ecosystem bootstrap failed")

    certification: dict[str, Any] | None = None
    if run_certification:
        certification = _run(
            [sys.executable, "-m", "tools.staging_certification"],
            env=runtime_env,
        )

    return {
        "status": "PASS",
        "evidence_type": "staging_integration",
        "environment": environment,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "alembic_before": before,
        "alembic_current": after,
        "alembic_expected_head": expected,
        "advisory_lock_id": LOCK_ID,
        "schema_check": schema,
        "bootstrap": bootstrap,
        "certification": certification,
        "certification_passed": certification is None or certification["returncode"] == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--top", type=int, default=100)
    parser.add_argument("--skip-certification", action="store_true")
    parser.add_argument("--output", default="staging_migration_evidence.json")
    args = parser.parse_args()

    try:
        payload = migrate_and_bootstrap(
            discover=args.discover,
            top=args.top,
            run_certification=not args.skip_certification,
        )
        code = 0
    except Exception as exc:
        payload = {
            "status": "BLOCKED",
            "evidence_type": "staging_integration",
            "environment": _environment(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "error": f"{type(exc).__name__}: {exc}",
        }
        code = 1

    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(payload, sort_keys=True, default=str))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
