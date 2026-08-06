#!/usr/bin/env python3
"""Print a non-secret database identity and schema fingerprint as JSON."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-head", default="")
    args = parser.parse_args()

    from config import resolve_database_url
    from scripts.assert_database_schema import _expected_head

    url = str(resolve_database_url(async_driver=False) or "").strip()
    if not url:
        print(json.dumps({"ok": False, "error": "DATABASE_URL is not configured"}))
        return 64

    import psycopg2

    with closing(psycopg2.connect(url, connect_timeout=10)) as connection:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT current_database(), current_user, inet_server_addr()::text,
                       inet_server_port(), pg_postmaster_start_time(),
                       (SELECT version_num FROM alembic_version LIMIT 1)
                """
            )
            database, user, address, port, started_at, revision = cursor.fetchone()

    expected = args.expect_head or _expected_head()
    material = f"{database}|{user}|{address}|{port}|{started_at.isoformat()}"
    fingerprint = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
    ok = str(revision or "") == expected
    print(
        json.dumps(
            {
                "ok": ok,
                "fingerprint": fingerprint,
                "database": database,
                "database_user": user,
                "server_address": address,
                "server_port": port,
                "postmaster_started_at": started_at.isoformat(),
                "alembic_current": revision,
                "alembic_expected_head": expected,
            },
            sort_keys=True,
            default=str,
        )
    )
    return 0 if ok else 78


if __name__ == "__main__":
    raise SystemExit(main())
