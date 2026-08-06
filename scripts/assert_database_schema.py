#!/usr/bin/env python3
"""Fail-fast database schema admission gate for every SignalRankAI runtime role.

This command never mutates the database. It proves that the configured runtime
PostgreSQL database is at the repository's single Alembic head and that the
critical unified-platform tables/columns exist before a worker, engine or web
process is allowed to start.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXIT_CONFIGURATION = 64
EXIT_UNREACHABLE = 69
EXIT_SCHEMA_MISMATCH = 78


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _expected_head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(ROOT / "alembic.ini"))
    heads = tuple(ScriptDirectory.from_config(cfg).get_heads())
    if len(heads) != 1:
        raise RuntimeError(f"repository must have exactly one Alembic head; found {heads}")
    return str(heads[0])


def _runtime_database_url() -> str:
    from config import resolve_database_url

    url = str(resolve_database_url(async_driver=False) or "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    return url


def check_schema() -> dict[str, Any]:
    expected = _expected_head()
    url = _runtime_database_url()

    import psycopg2

    query = """
        SELECT
          (SELECT version_num FROM alembic_version LIMIT 1) AS deployed_revision,
          to_regclass('public.subscription_products') IS NOT NULL AS subscription_products,
          to_regclass('public.instruments') IS NOT NULL AS instruments,
          to_regclass('public.webhook_deliveries') IS NOT NULL AS webhook_deliveries,
          to_regclass('public.auth_identities') IS NOT NULL AS auth_identities,
          to_regclass('public.user_sessions') IS NOT NULL AS user_sessions,
          EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'users'
              AND column_name = 'public_user_id'
          ) AS users_public_user_id,
          current_database() AS database_name,
          current_user AS database_user,
          inet_server_addr()::text AS server_address,
          inet_server_port() AS server_port
    """
    with closing(psycopg2.connect(url, connect_timeout=10)) as connection:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(query)
            row = cursor.fetchone()
            columns = [getattr(item, "name", item[0]) for item in cursor.description]

    record = dict(zip(columns, row, strict=True))
    deployed = str(record.pop("deployed_revision") or "")
    required = {
        key: bool(record.pop(key))
        for key in (
            "subscription_products",
            "instruments",
            "webhook_deliveries",
            "auth_identities",
            "user_sessions",
            "users_public_user_id",
        )
    }
    missing = sorted(name for name, present in required.items() if not present)
    ok = deployed == expected and not missing
    return {
        "status": "PASS" if ok else "BLOCKED",
        "ok": ok,
        "alembic_current": deployed or None,
        "alembic_expected_head": expected,
        "required_schema": required,
        "missing": missing,
        "database_name": record.get("database_name"),
        "database_user": record.get("database_user"),
        "server_address": record.get("server_address"),
        "server_port": record.get("server_port"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit one JSON object")
    args = parser.parse_args()

    try:
        payload = check_schema()
    except RuntimeError as exc:
        payload = {"status": "BLOCKED", "ok": False, "error": str(exc)}
        code = EXIT_CONFIGURATION
    except Exception as exc:  # pragma: no cover - environment/network dependent
        payload = {
            "status": "BLOCKED",
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        code = EXIT_UNREACHABLE
    else:
        code = 0 if payload["ok"] else EXIT_SCHEMA_MISMATCH

    if args.json:
        print(json.dumps(payload, sort_keys=True, default=str))
    else:
        detail = json.dumps(payload, sort_keys=True, default=str)
        stream = sys.stdout if code == 0 else sys.stderr
        print(f"[schema_gate] {detail}", file=stream)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
