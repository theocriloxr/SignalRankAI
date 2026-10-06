"""Hermetic verification of the complete current Alembic release chain."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HEAD = os.getenv("EXPECTED_ALEMBIC_HEAD", "0049_research_trial_ledger")


def main() -> int:
    cfg = Config(str(ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    heads = list(script.get_heads())
    if heads != [EXPECTED_HEAD]:
        raise SystemExit(f"ALEMBIC_HEAD_BLOCKED expected={[EXPECTED_HEAD]} actual={heads}")

    env = os.environ.copy()
    env["DATABASE_MIGRATION_URL"] = "postgresql+psycopg2://cleanroom:cleanroom@localhost/cleanroom"
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"ALEMBIC_OFFLINE_RENDER_BLOCKED exit={proc.returncode}")

    rendered = proc.stdout
    required = (
        "0045_mt5_credential_retirement",
        "credential_format",
        "trg_trading_account_ledger_immutable",
        "0046_decision_log",
        "CREATE TABLE IF NOT EXISTS decision_log",
        "0047_event_outbox",
        "0048_runtime_schema_bridge",
        "0049_research_trial_ledger",
        "reject_research_evidence_mutation",
        "CREATE TABLE IF NOT EXISTS event_outbox",
        "ix_event_outbox_claim",
    )
    missing = [marker for marker in required if marker not in rendered]
    if missing:
        raise SystemExit("ALEMBIC_OFFLINE_RENDER_BLOCKED missing=" + ",".join(missing))

    print(f"ALEMBIC_RELEASE_CHAIN_PASS head={EXPECTED_HEAD} required_markers={len(required)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
