"""Hermetic Alembic release-chain verification for broker credential envelopes."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HEAD = "0044_broker_credential_envelope"


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
        "0044_broker_credential_envelope",
        "credential_format",
        "credential_version",
        "credential_key_id",
        "credential_revision",
        "credential_rotated_at",
        "ck_broker_connections_credential_format",
        "ix_broker_connections_credential_key_id",
        "legacy_fernet",
        "trg_trading_account_ledger_immutable",
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
