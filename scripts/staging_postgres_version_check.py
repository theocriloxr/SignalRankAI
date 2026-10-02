#!/usr/bin/env python3
"""Fail-closed PostgreSQL major-version admission check for staging."""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone


async def main() -> int:
    from sqlalchemy import text
    from db.session import get_session
    from core.env import runtime_environment_name

    env = runtime_environment_name("")
    if env != "staging":
        raise RuntimeError(f"postgres_version_check_requires_staging got={env or 'unknown'}")

    expected = int(os.getenv("EXPECTED_POSTGRES_MAJOR", "18") or 18)
    async with get_session(
        priority="critical",
        label="certification.postgres_major",
        timeout_seconds=5.0,
        drop_if_busy=False,
    ) as session:
        raw = int((await session.execute(text("SHOW server_version_num"))).scalar_one())
        await session.rollback()

    actual = raw // 10000
    report = {
        "evidence_type": "staging_postgres_major",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": env,
        "expected_major": expected,
        "actual_major": actual,
        "status": "PASS" if actual == expected else "FAILED",
    }
    print("STAGING_POSTGRES_MAJOR " + json.dumps(report, sort_keys=True))
    if actual != expected:
        raise RuntimeError(f"postgres_major_mismatch expected={expected} actual={actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
