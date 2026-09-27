"""Read-only staging demo-account readiness preflight.

Outputs counts and blocker codes only. It never prints broker account IDs,
credentials, connection IDs, external account references, passwords, tokens or
other secret material, and it never places or modifies an order.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from db.session import get_session


EXPECTED_HEAD = "0045_mt5_credential_retirement"
_READY_CONNECTION_STATUSES = {"verified", "ready", "linked"}
_CREDENTIAL_READY_FORMATS = {"envelope_v1", "provider_managed"}


def _environment() -> str:
    return str(
        os.getenv("RAILWAY_ENVIRONMENT_NAME")
        or os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("APP_ENV")
        or ""
    ).strip().lower()


async def collect_demo_account_preflight() -> dict[str, Any]:
    environment = _environment()
    if environment != "staging":
        raise RuntimeError(
            f"demo_account_preflight_requires_staging got={environment or 'unknown'}"
        )

    async with get_session(
        label="demo_account_preflight",
        timeout_seconds=8.0,
    ) as session:
        head = (
            await session.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one_or_none()

        summary = (
            await session.execute(
                text(
                    """
                    SELECT
                        COUNT(*)::int AS total_connections,
                        COUNT(*) FILTER (
                            WHERE UPPER(COALESCE(p.account_mode, '')) = 'DEMO'
                        )::int AS demo_policy_connections,
                        COUNT(*) FILTER (
                            WHERE UPPER(COALESCE(p.account_mode, '')) = 'DEMO'
                              AND LOWER(COALESCE(c.status, '')) IN ('verified','ready','linked')
                              AND c.verified_at IS NOT NULL
                        )::int AS demo_verified_connections,
                        COUNT(*) FILTER (
                            WHERE UPPER(COALESCE(p.account_mode, '')) = 'DEMO'
                              AND (
                                LOWER(COALESCE(c.credential_format, '')) IN ('envelope_v1','provider_managed')
                              )
                        )::int AS demo_credential_ready_connections,
                        COUNT(*) FILTER (
                            WHERE UPPER(COALESCE(p.account_mode, '')) = 'DEMO'
                              AND COALESCE(c.execution_enabled, false)
                        )::int AS demo_execution_enabled_connections,
                        COUNT(*) FILTER (
                            WHERE UPPER(COALESCE(p.account_mode, '')) = 'DEMO'
                              AND UPPER(COALESCE(r.status, '')) = 'HEALTHY'
                        )::int AS demo_healthy_reconciliation_connections,
                        COUNT(*) FILTER (
                            WHERE UPPER(COALESCE(p.account_mode, '')) = 'DEMO'
                              AND p.frozen_at IS NOT NULL
                        )::int AS demo_frozen_policy_connections,
                        COUNT(*) FILTER (
                            WHERE UPPER(COALESCE(p.account_mode, '')) = 'DEMO'
                              AND UPPER(COALESCE(p.execution_permission, '')) IN (
                                'MANUAL','ASSISTED_EXECUTION','AUTO_EXECUTION'
                              )
                        )::int AS demo_execution_permission_connections
                    FROM broker_connections c
                    LEFT JOIN trading_account_policies p
                      ON p.connection_id = c.connection_id
                     AND p.user_id = c.user_id
                    LEFT JOIN broker_reconciliation_state r
                      ON r.connection_id = c.connection_id
                     AND r.user_id = c.user_id
                    """
                )
            )
        ).mappings().one()

        providers = (
            await session.execute(
                text(
                    """
                    SELECT
                        LOWER(COALESCE(c.platform, 'unknown')) AS platform,
                        LOWER(COALESCE(c.connector, 'unknown')) AS connector,
                        COUNT(*)::int AS connections
                    FROM broker_connections c
                    JOIN trading_account_policies p
                      ON p.connection_id = c.connection_id
                     AND p.user_id = c.user_id
                    WHERE UPPER(COALESCE(p.account_mode, '')) = 'DEMO'
                    GROUP BY 1, 2
                    ORDER BY 1, 2
                    """
                )
            )
        ).mappings().all()
        await session.rollback()

    counts = {key: int(value or 0) for key, value in dict(summary).items()}
    blockers: list[str] = []
    if str(head or "") != EXPECTED_HEAD:
        blockers.append("schema_head_mismatch")
    if counts["demo_policy_connections"] <= 0:
        blockers.append("demo_account_not_connected")
    if counts["demo_verified_connections"] <= 0:
        blockers.append("demo_account_not_read_only_verified")
    if counts["demo_credential_ready_connections"] <= 0:
        blockers.append("demo_account_credentials_not_ready")
    if counts["demo_healthy_reconciliation_connections"] <= 0:
        blockers.append("demo_reconciliation_not_healthy")
    if counts["demo_frozen_policy_connections"] > 0:
        blockers.append("demo_policy_frozen")
    if counts["demo_execution_permission_connections"] <= 0:
        blockers.append("demo_execution_permission_not_configured")

    # A preflight must never silently turn execution on. Existing enabled rows
    # are reported for operator review but not treated as certification proof.
    if counts["demo_execution_enabled_connections"] > 0:
        blockers.append("demo_execution_already_enabled_review_required")

    return {
        "status": "PASS" if not blockers else "BLOCKED",
        "environment": environment,
        "alembic_head": str(head or ""),
        "expected_alembic_head": EXPECTED_HEAD,
        "counts": counts,
        "providers": [
            {
                "platform": str(row["platform"]),
                "connector": str(row["connector"]),
                "connections": int(row["connections"]),
            }
            for row in providers
        ],
        "blockers": blockers,
        "activation_performed": False,
        "orders_placed": 0,
        "secrets_returned": False,
    }


async def _main() -> int:
    report = await collect_demo_account_preflight()
    print("DEMO_ACCOUNT_PREFLIGHT " + json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
