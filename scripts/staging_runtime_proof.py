#!/usr/bin/env python3
"""Database-backed SignalRankAI staging proof.

This command is deliberately read-only.  It verifies the real PostgreSQL
catalogue and optionally requires recent end-to-end runtime evidence.
Credentials are never printed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXPECTED_HEAD = "0038_account_security_product"


def _raw(name: str) -> str:
    return str(os.getenv(name) or "").strip().strip('"').strip("'")


def _dsn() -> str:
    from db.database_urls import normalize_psycopg2_dsn

    raw = _raw("DATABASE_MIGRATION_URL") or _raw("DATABASE_DIRECT_URL") or _raw("DATABASE_URL")
    if not raw:
        raise RuntimeError("database URL is not configured")
    return normalize_psycopg2_dsn(raw)


def _safe_error(exc: Exception) -> str:
    return type(exc).__name__


def collect(window_hours: int = 6) -> dict[str, Any]:
    import psycopg2
    from core.tier_policy import TIER_ORDER, Tier, get_entitlements
    from ml.schema_version import get_feature_columns

    expected_features = sum(
        len(get_entitlements(tier).features)
        for tier in TIER_ORDER
        if tier not in {Tier.ADMIN, Tier.OWNER}
    )
    expected_controls = 16 * len([tier for tier in TIER_ORDER if tier not in {Tier.ADMIN, Tier.OWNER}])
    expected_feature_defs = len(get_feature_columns())

    report: dict[str, Any] = {
        "evidence_type": "staging_database_runtime_proof",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_hours": max(1, int(window_hours)),
        "expected_head": EXPECTED_HEAD,
    }
    with psycopg2.connect(_dsn(), connect_timeout=15) as conn:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user, COALESCE(inet_server_addr()::text,'local'), inet_server_port()")
            db_name, db_user, db_host, db_port = cur.fetchone()
            report["database"] = {
                "name": str(db_name),
                "user": str(db_user),
                "server_address": str(db_host),
                "server_port": int(db_port or 0),
            }
            cur.execute("SELECT version_num FROM alembic_version LIMIT 1")
            row = cur.fetchone()
            report["alembic_current"] = str(row[0]) if row else None

            cur.execute("""
                SELECT
                  to_regclass('public.subscription_products') IS NOT NULL,
                  to_regclass('public.subscription_prices') IS NOT NULL,
                  to_regclass('public.subscription_entitlements') IS NOT NULL,
                  to_regclass('public.instruments') IS NOT NULL,
                  to_regclass('public.provider_instruments') IS NOT NULL,
                  to_regclass('public.auth_identities') IS NOT NULL,
                  to_regclass('public.user_sessions') IS NOT NULL,
                  to_regclass('public.webhook_deliveries') IS NOT NULL,
                  to_regclass('public.payment_receipts') IS NOT NULL,
                  to_regclass('public.email_outbox') IS NOT NULL
            """)
            values = cur.fetchone()
            names = (
                "subscription_products", "subscription_prices", "subscription_entitlements",
                "instruments", "provider_instruments", "auth_identities", "user_sessions",
                "webhook_deliveries", "payment_receipts", "email_outbox",
            )
            report["required_tables"] = dict(zip(names, map(bool, values)))

            cur.execute("""
                SELECT EXISTS (
                  SELECT 1 FROM information_schema.columns
                  WHERE table_schema='public' AND table_name='users' AND column_name='public_user_id'
                )
            """)
            report["users_public_user_id"] = bool(cur.fetchone()[0])

            queries = {
                "active_products": "SELECT COUNT(*) FROM subscription_products WHERE active=TRUE",
                "active_prices": "SELECT COUNT(*) FROM subscription_prices WHERE effective_until IS NULL",
                "feature_entitlements": "SELECT COUNT(*) FROM subscription_entitlements WHERE entitlement_key LIKE 'feature.%' AND enabled=TRUE",
                "control_entitlements": "SELECT COUNT(*) FROM subscription_entitlements WHERE entitlement_key NOT LIKE 'feature.%'",
                "feature_definitions": "SELECT COUNT(*) FROM feature_definitions WHERE feature_version='3'",
                "strategy_versions": "SELECT COUNT(*) FROM strategy_versions",
                "active_instruments": "SELECT COUNT(*) FROM instruments WHERE active=TRUE",
                "tradable_instruments": "SELECT COUNT(*) FROM instruments WHERE active=TRUE AND tradable=TRUE",
                "provider_mappings": "SELECT COUNT(*) FROM provider_instruments WHERE data_enabled=TRUE",
                "canonical_users": "SELECT COUNT(*) FROM users WHERE public_user_id IS NOT NULL",
                "auth_identities": "SELECT COUNT(*) FROM auth_identities",
            }
            counts: dict[str, int] = {}
            for key, sql in queries.items():
                cur.execute(sql)
                counts[key] = int(cur.fetchone()[0] or 0)
            report["catalogue_counts"] = counts
            report["catalogue_minimums"] = {
                "active_products": 6,
                "active_prices": 6,
                "feature_entitlements": expected_features,
                "control_entitlements": expected_controls,
                "feature_definitions": expected_feature_defs,
                "strategy_versions": 15,
                "tradable_instruments": 1,
                "provider_mappings": 1,
            }

            cur.execute("""
                SELECT LOWER(asset_class), COUNT(*)
                FROM instruments
                WHERE active=TRUE AND tradable=TRUE
                GROUP BY LOWER(asset_class)
                ORDER BY LOWER(asset_class)
            """)
            report["tradable_instruments_by_asset_class"] = {str(k): int(v) for k, v in cur.fetchall()}

            hours = max(1, int(window_hours))
            cur.execute("SELECT COUNT(*) FROM signals WHERE created_at >= NOW() - (%s * INTERVAL '1 hour')", (hours,))
            recent_signals = int(cur.fetchone()[0] or 0)
            cur.execute("""
                SELECT COUNT(*) FROM signal_deliveries
                WHERE sent_ok=TRUE
                  AND delivery_confirmed_at IS NOT NULL
                  AND telegram_chat_id IS NOT NULL
                  AND telegram_message_id IS NOT NULL
                  AND delivery_confirmed_at >= NOW() - (%s * INTERVAL '1 hour')
            """, (hours,))
            confirmed_deliveries = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT COUNT(*) FROM paper_positions WHERE opened_at >= NOW() - (%s * INTERVAL '1 hour')", (hours,))
            recent_paper = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT COUNT(*) FROM outcomes WHERE closed_at >= NOW() - (%s * INTERVAL '1 hour')", (hours,))
            recent_outcomes = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT COUNT(*) FROM payment_receipts WHERE payment_date >= NOW() - (%s * INTERVAL '1 hour')", (hours,))
            recent_receipts = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT COUNT(*) FROM email_outbox WHERE status='sent' AND sent_at >= NOW() - (%s * INTERVAL '1 hour')", (hours,))
            recent_emails = int(cur.fetchone()[0] or 0)
            cur.execute("""
                SELECT COUNT(*) FROM (
                  SELECT user_id, signal_id FROM signal_deliveries
                  GROUP BY user_id, signal_id HAVING COUNT(*) > 1
                ) d
            """)
            duplicate_deliveries = int(cur.fetchone()[0] or 0)
            cur.execute("""
                SELECT COUNT(*) FROM (
                  SELECT user_id, signal_id FROM paper_positions
                  GROUP BY user_id, signal_id HAVING COUNT(*) > 1
                ) p
            """)
            duplicate_paper = int(cur.fetchone()[0] or 0)
            report["runtime"] = {
                "recent_signals": recent_signals,
                "confirmed_telegram_deliveries": confirmed_deliveries,
                "recent_paper_positions": recent_paper,
                "recent_outcomes": recent_outcomes,
                "recent_payment_receipts": recent_receipts,
                "recent_sent_emails": recent_emails,
                "duplicate_delivery_groups": duplicate_deliveries,
                "duplicate_paper_position_groups": duplicate_paper,
            }
    return report


def evaluate(
    report: dict[str, Any],
    *,
    require_runtime: bool = False,
    require_payment: bool = False,
    require_email: bool = False,
) -> list[str]:
    blockers: list[str] = []
    if report.get("alembic_current") != EXPECTED_HEAD:
        blockers.append(f"alembic:{report.get('alembic_current')}!={EXPECTED_HEAD}")
    for name, present in (report.get("required_tables") or {}).items():
        if not present:
            blockers.append(f"missing_table:{name}")
    if not report.get("users_public_user_id"):
        blockers.append("missing_column:users.public_user_id")
    counts = report.get("catalogue_counts") or {}
    for key, minimum in (report.get("catalogue_minimums") or {}).items():
        if int(counts.get(key) or 0) < int(minimum):
            blockers.append(f"{key}:{int(counts.get(key) or 0)}<{int(minimum)}")
    runtime = report.get("runtime") or {}
    if int(runtime.get("duplicate_delivery_groups") or 0) != 0:
        blockers.append("duplicate_delivery_groups")
    if int(runtime.get("duplicate_paper_position_groups") or 0) != 0:
        blockers.append("duplicate_paper_position_groups")
    if require_runtime:
        if int(runtime.get("recent_signals") or 0) < 1:
            blockers.append("runtime:no_recent_signal")
        if int(runtime.get("confirmed_telegram_deliveries") or 0) < 1:
            blockers.append("runtime:no_confirmed_telegram_delivery")
        if int(runtime.get("recent_paper_positions") or 0) < 1:
            blockers.append("runtime:no_recent_paper_position")
    if require_payment and int(runtime.get("recent_payment_receipts") or 0) < 1:
        blockers.append("runtime:no_recent_payment_receipt")
    if require_email and int(runtime.get("recent_sent_emails") or 0) < 1:
        blockers.append("runtime:no_recent_sent_email")
    return blockers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window-hours", type=int, default=6)
    parser.add_argument("--require-runtime", action="store_true")
    parser.add_argument("--require-payment", action="store_true")
    parser.add_argument("--require-email", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    try:
        report = collect(args.window_hours)
        blockers = evaluate(
            report,
            require_runtime=args.require_runtime,
            require_payment=args.require_payment,
            require_email=args.require_email,
        )
        report["blockers"] = blockers
        report["status"] = "PASS" if not blockers else "BLOCKED"
        code = 0 if not blockers else 1
    except Exception as exc:
        report = {
            "evidence_type": "staging_database_runtime_proof",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "BLOCKED",
            "blockers": [f"collector:{_safe_error(exc)}"],
        }
        code = 1
    payload = json.dumps(report, indent=2, sort_keys=True, default=str)
    print(payload)
    if args.output:
        path = Path(args.output)
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
