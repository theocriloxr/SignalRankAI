#!/usr/bin/env python3
"""Read-only diagnosis for legacy payment_receipts schema/data drift."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text


def _sync_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)


def collect(database_url: str) -> dict[str, Any]:
    engine = create_engine(_sync_url(database_url), pool_pre_ping=True)
    report: dict[str, Any] = {"table_exists": False}
    with engine.connect() as conn:
        exists = bool(conn.execute(text("SELECT to_regclass('payment_receipts') IS NOT NULL")).scalar())
        report["table_exists"] = exists
        if not exists:
            return report
        report["columns"] = [dict(row._mapping) for row in conn.execute(text("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema=current_schema() AND table_name='payment_receipts'
            ORDER BY ordinal_position
        """))]
        report["indexes"] = [dict(row._mapping) for row in conn.execute(text("""
            SELECT indexname, indexdef FROM pg_indexes
            WHERE schemaname=current_schema() AND tablename='payment_receipts'
            ORDER BY indexname
        """))]
        report["constraints"] = [dict(row._mapping) for row in conn.execute(text("""
            SELECT conname, contype, pg_get_constraintdef(oid) AS definition
            FROM pg_constraint
            WHERE conrelid='payment_receipts'::regclass
            ORDER BY conname
        """))]
        report["row_count"] = int(conn.execute(text("SELECT COUNT(*) FROM payment_receipts")).scalar() or 0)
        report["duplicate_receipt_numbers"] = [dict(row._mapping) for row in conn.execute(text("""
            SELECT receipt_number, COUNT(*) AS row_count
            FROM payment_receipts
            WHERE receipt_number IS NOT NULL
            GROUP BY receipt_number HAVING COUNT(*) > 1
            ORDER BY row_count DESC, receipt_number LIMIT 100
        """))]
        report["duplicate_provider_references"] = [dict(row._mapping) for row in conn.execute(text("""
            SELECT provider, payment_reference, COUNT(*) AS row_count
            FROM payment_receipts
            WHERE provider IS NOT NULL AND payment_reference IS NOT NULL
            GROUP BY provider, payment_reference HAVING COUNT(*) > 1
            ORDER BY row_count DESC, provider, payment_reference LIMIT 100
        """))]
        report["incomplete_rows"] = int(conn.execute(text("""
            SELECT COUNT(*) FROM payment_receipts
            WHERE receipt_number IS NULL OR user_id IS NULL OR payment_reference IS NULL
               OR plan IS NULL OR amount IS NULL
        """)).scalar() or 0)
    engine.dispose()
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("DATABASE_URL is required")
    report = collect(args.database_url)
    payload = json.dumps(report, indent=2, default=str, sort_keys=True)
    print(payload)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
