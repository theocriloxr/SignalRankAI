"""Read-only broker credential migration inventory.

Outputs counts only. It never selects, decrypts, logs, hashes, fingerprints or
returns credential ciphertext, keys, passwords, logins, servers or account IDs.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
import os
from typing import Any


def _database_url() -> str:
    return str(
        os.getenv("DATABASE_MIGRATION_URL")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()


def collect() -> dict[str, Any]:
    url = _database_url()
    if not url:
        raise RuntimeError("database_url_not_configured")

    import psycopg2

    with closing(psycopg2.connect(url, connect_timeout=10)) as connection:
        connection.set_session(readonly=True, autocommit=True)
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = '10000ms'")

            cursor.execute(
                """
                SELECT COALESCE(NULLIF(BTRIM(credential_format), ''), 'none') AS format,
                       COUNT(*)::bigint
                FROM broker_connections
                GROUP BY 1
                ORDER BY 1
                """
            )
            format_counts = {
                str(name): int(count or 0)
                for name, count in cursor.fetchall()
            }

            cursor.execute(
                """
                SELECT
                  COUNT(*)::bigint,
                  COUNT(*) FILTER (
                    WHERE password_encrypted IS NULL
                       OR BTRIM(password_encrypted) = ''
                  )::bigint,
                  COUNT(*) FILTER (
                    WHERE password_encrypted IS NOT NULL
                      AND BTRIM(password_encrypted) <> ''
                  )::bigint
                FROM mt5_credentials
                """
            )
            total, scrubbed, password_rows = cursor.fetchone()

            cursor.execute(
                """
                SELECT COUNT(*)::bigint
                FROM mt5_credentials AS legacy
                WHERE legacy.password_encrypted IS NOT NULL
                  AND BTRIM(legacy.password_encrypted) <> ''
                  AND EXISTS (
                    SELECT 1
                    FROM broker_connections AS canonical
                    WHERE canonical.user_id = legacy.user_id
                      AND LOWER(COALESCE(canonical.platform, '')) = 'mt5'
                      AND LOWER(COALESCE(canonical.connector, '')) = 'metaapi'
                      AND canonical.credential_format = 'envelope_v1'
                      AND canonical.secret_encrypted IS NOT NULL
                      AND BTRIM(canonical.secret_encrypted) <> ''
                  )
                """
            )
            duplicate_password_rows = int(cursor.fetchone()[0] or 0)

            cursor.execute(
                """
                SELECT COUNT(*)::bigint
                FROM mt5_credentials AS legacy
                WHERE legacy.password_encrypted IS NOT NULL
                  AND BTRIM(legacy.password_encrypted) <> ''
                  AND NOT EXISTS (
                    SELECT 1
                    FROM broker_connections AS canonical
                    WHERE canonical.user_id = legacy.user_id
                      AND LOWER(COALESCE(canonical.platform, '')) = 'mt5'
                      AND LOWER(COALESCE(canonical.connector, '')) = 'metaapi'
                      AND canonical.credential_format = 'envelope_v1'
                      AND canonical.secret_encrypted IS NOT NULL
                      AND BTRIM(canonical.secret_encrypted) <> ''
                  )
                """
            )
            unmigrated_mt5_password_rows = int(cursor.fetchone()[0] or 0)

            cursor.execute(
                """
                SELECT COUNT(*)::bigint
                FROM broker_connections
                WHERE credential_format = 'legacy_fernet'
                  AND secret_encrypted IS NOT NULL
                  AND BTRIM(secret_encrypted) <> ''
                """
            )
            legacy_broker_rows = int(cursor.fetchone()[0] or 0)

    password_rows_i = int(password_rows or 0)
    return {
        "evidence_type": "broker_credential_migration_inventory",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "credential_format_counts": format_counts,
        "canonical_legacy_fernet_rows": legacy_broker_rows,
        "legacy_mt5": {
            "total_rows": int(total or 0),
            "scrubbed_or_empty_password_rows": int(scrubbed or 0),
            "rows_with_password_ciphertext": password_rows_i,
            "duplicate_rows_already_backed_by_envelope": duplicate_password_rows,
            "rows_without_canonical_envelope": unmigrated_mt5_password_rows,
        },
        "ready_for_live_money_credentials": (
            legacy_broker_rows == 0 and password_rows_i == 0
        ),
    }


def _emit_safe_log_summary(report: dict[str, Any]) -> None:
    """Emit only aggregate counts with neutral labels for deployment evidence."""
    legacy = dict(report.get("legacy_mt5") or {})
    formats = dict(report.get("credential_format_counts") or {})
    print(f"BROKER_INVENTORY_STATUS={report.get('status') or 'UNKNOWN'}")
    print(
        "BROKER_CANONICAL_ENVELOPE_V1_ROWS="
        f"{int(formats.get('envelope_v1') or 0)}"
    )
    print(
        "BROKER_CANONICAL_LEGACY_ROWS="
        f"{int(report.get('canonical_legacy_fernet_rows') or 0)}"
    )
    print(
        "MT5_LEGACY_SECRET_ROWS="
        f"{int(legacy.get('rows_with_password_ciphertext') or 0)}"
    )
    print(
        "MT5_DUPLICATE_SECRET_ROWS="
        f"{int(legacy.get('duplicate_rows_already_backed_by_envelope') or 0)}"
    )
    print(
        "MT5_UNMIGRATED_SECRET_ROWS="
        f"{int(legacy.get('rows_without_canonical_envelope') or 0)}"
    )
    print(
        "BROKER_LIVE_MONEY_SECRET_READINESS="
        f"{1 if report.get('ready_for_live_money_credentials') else 0}"
    )


def main() -> int:
    try:
        report = collect()
    except Exception as exc:
        report = {
            "evidence_type": "broker_credential_migration_inventory",
            "status": "BLOCKED",
            "error": type(exc).__name__,
        }
        _emit_safe_log_summary(report)
        print(json.dumps(report, sort_keys=True))
        return 1

    report["status"] = (
        "PASS" if report["ready_for_live_money_credentials"] else "ROTATION_REQUIRED"
    )
    _emit_safe_log_summary(report)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
