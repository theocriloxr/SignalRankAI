#!/usr/bin/env python3
"""Staging-only PostgreSQL backup/restore drill.

The drill:
1. takes a consistent custom-format pg_dump of the configured staging database;
2. creates a disposable database on the same PostgreSQL cluster;
3. restores the dump into that isolated target;
4. verifies Alembic head and critical SignalRank schema objects;
5. emits only secret-free timing/hash/count evidence;
6. force-drops the disposable database in a finally block.

It never mutates the source database and refuses to run outside Railway staging.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit, urlunsplit


EXPECTED_HEAD = os.getenv("EXPECTED_ALEMBIC_HEAD", "0045_mt5_credential_retirement")
ACK = "I_UNDERSTAND_THIS_CREATES_AND_DROPS_AN_ISOLATED_STAGING_DATABASE"
SAFE_DB_RE = re.compile(r"^signalrank_restore_drill_[0-9]{8}_[0-9]{6}_[0-9]+$")


def _normalize_url(raw: str) -> str:
    value = str(raw or "").strip()
    if value.startswith("postgres://"):
        value = "postgresql://" + value[len("postgres://") :]
    for suffix in ("+asyncpg", "+psycopg2", "+psycopg"):
        value = value.replace("postgresql" + suffix + "://", "postgresql://", 1)
    if not value.startswith("postgresql://"):
        raise RuntimeError("restore_drill_requires_postgresql_url")
    return value


def _replace_database(url: str, database: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/" + database, parts.query, ""))


def _run(args: list[str], *, timeout: int = 900, capture: bool = True) -> str:
    proc = subprocess.run(
        args,
        text=True,
        capture_output=capture,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or "")[-2000:]
        raise RuntimeError(
            f"command_failed tool={Path(args[0]).name} exit={proc.returncode} detail={stderr}"
        )
    return (proc.stdout or "").strip()


def _psql(url: str, sql: str) -> str:
    return _run(
        ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-At", url, "-c", sql],
        timeout=180,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_environment() -> None:
    environment = str(
        os.getenv("RAILWAY_ENVIRONMENT_NAME")
        or os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("APP_ENV")
        or ""
    ).strip().lower()
    profile = str(os.getenv("SIGNALRANK_ENV_PROFILE") or "").strip().lower()
    if environment != "staging":
        raise RuntimeError(f"restore_drill_requires_staging environment={environment or 'unknown'}")
    if profile != "staging-certification":
        raise RuntimeError("restore_drill_requires_staging_certification_profile")
    if os.getenv("STAGING_BACKUP_RESTORE_DRILL_ACK") != ACK:
        raise RuntimeError("restore_drill_ack_missing")
    for flag in (
        "REAL_EXECUTION_ENABLED",
        "AUTO_EXECUTION_ENABLED",
        "AUTO_TRADE_ENABLED",
        "COPY_TRADE_ENABLED",
        "BYBIT_EXECUTION_ENABLED",
        "MT5_ALLOW_LIVE_ACCOUNTS",
        "HYPERLIQUID_MAINNET_EXECUTION_ENABLED",
        "REAL_PAYOUTS_ENABLED",
        "AUTOMATIC_PAYOUTS_ENABLED",
        "PAYSTACK_TRANSFERS_ENABLED",
        "PAYMENTS_PUBLIC_ENABLED",
    ):
        if str(os.getenv(flag) or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}:
            raise RuntimeError(f"restore_drill_requires_flag_off:{flag}")


def _cleanup_database(admin_url: str, target_db: str) -> None:
    if not SAFE_DB_RE.fullmatch(target_db):
        raise RuntimeError("unsafe_restore_database_name")
    _psql(
        admin_url,
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname='{target_db}' AND pid <> pg_backend_pid()",
    )
    # DROP DATABASE must be its own top-level statement; combining it with the
    # terminate query makes PostgreSQL treat the -c payload as one transaction.
    _psql(admin_url, f'DROP DATABASE IF EXISTS "{target_db}" WITH (FORCE)')


def main() -> int:
    _safe_environment()
    source = _normalize_url(
        os.getenv("SOURCE_DATABASE_URL")
        or os.getenv("DATABASE_MIGRATION_URL")
        or os.getenv("DATABASE_URL")
        or ""
    )
    source_parts = urlsplit(source)
    source_db = source_parts.path.lstrip("/")
    if not source_db:
        raise RuntimeError("source_database_name_missing")

    stamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    target_db = f"signalrank_restore_drill_{stamp}_{os.getpid()}"
    if not SAFE_DB_RE.fullmatch(target_db):
        raise RuntimeError("unsafe_restore_database_name")

    admin_url = _replace_database(source, "postgres")

    cleanup_target = str(os.getenv("STAGING_RESTORE_CLEANUP_TARGET") or "").strip()
    if cleanup_target:
        if not SAFE_DB_RE.fullmatch(cleanup_target):
            raise RuntimeError("unsafe_restore_database_name")
        _cleanup_database(admin_url, cleanup_target)
        print(
            "STAGING_RESTORE_CLEANUP_PASS "
            + json.dumps({"target_database": cleanup_target}, sort_keys=True),
            flush=True,
        )
        return 0

    target_url = _replace_database(source, target_db)

    report: dict[str, object] = {
        "evidence_type": "staging_backup_restore_drill",
        "status": "RUNNING",
        "expected_alembic_head": EXPECTED_HEAD,
        "source_database_fingerprint": hashlib.sha256(
            f"{source_parts.hostname}:{source_parts.port or 5432}/{source_db}".encode()
        ).hexdigest()[:20],
        "target_database": target_db,
        "production_mutation": False,
        "source_database_mutation": False,
        "live_execution": False,
    }

    created = False
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="signalrank-restore-drill-") as temp_dir:
            dump_path = Path(temp_dir) / "staging.dump"

            dump_started = time.monotonic()
            _run(
                [
                    "pg_dump",
                    "--format=custom",
                    "--compress=6",
                    "--no-owner",
                    "--no-privileges",
                    "--file",
                    str(dump_path),
                    source,
                ],
                timeout=1800,
            )
            report["dump_seconds"] = round(time.monotonic() - dump_started, 3)
            report["dump_bytes"] = dump_path.stat().st_size
            report["dump_sha256"] = _sha256(dump_path)

            _psql(admin_url, f'CREATE DATABASE "{target_db}"')
            created = True

            restore_started = time.monotonic()
            _run(
                [
                    "pg_restore",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-privileges",
                    "--dbname",
                    target_url,
                    str(dump_path),
                ],
                timeout=1800,
            )
            report["restore_seconds"] = round(time.monotonic() - restore_started, 3)

            restored_head = _psql(
                target_url,
                "SELECT version_num FROM alembic_version ORDER BY version_num LIMIT 1",
            )
            report["restored_alembic_head"] = restored_head
            if restored_head != EXPECTED_HEAD:
                raise RuntimeError(
                    f"restored_alembic_head_mismatch expected={EXPECTED_HEAD} actual={restored_head}"
                )

            critical_tables = (
                "users",
                "signals",
                "broker_connections",
                "trading_account_policies",
                "broker_reconciliation_state",
                "trading_account_ledger_entries",
                "broker_execution_decisions",
                "mt5_executions",
                "broker_executions",
            )
            missing: list[str] = []
            counts: dict[str, int] = {}
            for table in critical_tables:
                exists = _psql(
                    target_url,
                    "SELECT CASE WHEN to_regclass('public."
                    + table
                    + "') IS NULL THEN '0' ELSE '1' END",
                )
                if exists != "1":
                    missing.append(table)
                    continue
                count_text = _psql(target_url, f'SELECT COUNT(*) FROM "{table}"')
                counts[table] = int(count_text or "0")

            if missing:
                raise RuntimeError("restored_required_tables_missing:" + ",".join(missing))

            immutable_trigger = _psql(
                target_url,
                """
                SELECT COUNT(*)
                FROM pg_trigger t
                JOIN pg_class c ON c.oid=t.tgrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public'
                  AND c.relname='trading_account_ledger_entries'
                  AND t.tgname='trg_trading_account_ledger_immutable'
                  AND NOT t.tgisinternal
                """,
            )
            if int(immutable_trigger or "0") != 1:
                raise RuntimeError("restored_account_ledger_immutability_guard_missing")

            report["critical_table_counts"] = counts
            report["ledger_immutability_trigger"] = True
            report["status"] = "PASS"
            report["total_seconds"] = round(time.monotonic() - started, 3)
            print(
                "STAGING_BACKUP_RESTORE_VERIFIED_PENDING_CLEANUP "
                + json.dumps(report, sort_keys=True),
                flush=True,
            )
            return 0
    finally:
        if created:
            try:
                _cleanup_database(admin_url, target_db)
                report["cleanup"] = "PASS"
                if report.get("status") == "PASS":
                    print(
                        "STAGING_BACKUP_RESTORE_DRILL_PASS "
                        + json.dumps(report, sort_keys=True),
                        flush=True,
                    )
            except Exception as exc:
                report["cleanup"] = "FAILED"
                print(
                    "STAGING_BACKUP_RESTORE_DRILL_CLEANUP_ERROR "
                    + json.dumps({"type": type(exc).__name__, "message": str(exc)[:500]}, sort_keys=True),
                    file=sys.stderr,
                    flush=True,
                )


if __name__ == "__main__":
    raise SystemExit(main())
