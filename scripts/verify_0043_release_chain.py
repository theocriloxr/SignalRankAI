"""Hermetic Alembic release-chain verification for the 2026-09-25 branch.

No network or database connection is used. Alembic renders the full configured
migration chain in offline mode against a fake PostgreSQL DSN, then this script
verifies the exact expected head and the critical 0043 SQL objects.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HEAD = "0043_account_execution_policy"


def main() -> int:
    cfg = Config(str(ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    heads = list(script.get_heads())
    if heads != [EXPECTED_HEAD]:
        raise SystemExit(
            f"ALEMBIC_HEAD_BLOCKED expected={[EXPECTED_HEAD]} actual={heads}"
        )

    env = os.environ.copy()
    env["DATABASE_MIGRATION_URL"] = (
        "postgresql+psycopg2://cleanroom:cleanroom@localhost/cleanroom"
    )
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(
            f"ALEMBIC_OFFLINE_RENDER_BLOCKED exit={proc.returncode}"
        )

    rendered = proc.stdout
    required = (
        "CREATE TABLE trading_account_policies",
        "CREATE TABLE broker_reconciliation_state",
        "CREATE TABLE trading_account_ledger_entries",
        "CREATE TABLE broker_execution_decisions",
        "trg_trading_account_ledger_immutable",
        "prevent_trading_account_ledger_mutation",
        "RETURNS trigger AS $",
        "$ LANGUAGE plpgsql",
        "ix_trading_account_ledger_account_created",
        "ix_broker_executions_connection_status",
        "ix_mt5_executions_connection_status",
    )
    missing = [marker for marker in required if marker not in rendered]
    if missing:
        raise SystemExit(
            "ALEMBIC_OFFLINE_RENDER_BLOCKED missing=" + ",".join(missing)
        )

    print(
        "ALEMBIC_RELEASE_CHAIN_PASS "
        f"head={EXPECTED_HEAD} required_markers={len(required)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
