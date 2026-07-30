"""Read-only migration-chain audit used by the release guard."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def audit_versions(root: Path = ROOT) -> dict[str, object]:
    directory = root / "db" / "migrations" / "versions"
    revisions: dict[str, str | None] = {}
    errors: list[str] = []
    for path in sorted(directory.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            values: dict[str, object] = {}
            for node in tree.body:
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in {"revision", "down_revision"}:
                    values[node.targets[0].id] = ast.literal_eval(node.value)
            revision = str(values.get("revision") or "")
            down = values.get("down_revision")
            down_value = str(down) if down not in (None, "") else None
            if not revision:
                errors.append(f"{path.name}: missing revision")
            elif len(revision) > 32:
                errors.append(f"{path.name}: revision exceeds 32 chars")
            else:
                revisions[revision] = down_value
        except Exception as exc:
            errors.append(f"{path.name}: {type(exc).__name__}")
    heads = sorted(revision for revision in revisions if revision not in set(value for value in revisions.values() if value))
    missing_parents = sorted(value for value in revisions.values() if value and value not in revisions)
    errors.extend(f"missing parent: {parent}" for parent in missing_parents)
    return {"ok": not errors and len(heads) == 1, "heads": heads, "revisions": len(revisions), "errors": errors}



def audit_signal_runtime_contract(root: Path = ROOT) -> dict[str, object]:
    """Compare canonical Signal ORM columns with the rendered Alembic chain."""
    env = os.environ.copy()
    env["DATABASE_MIGRATION_URL"] = "postgresql+psycopg2://audit:audit@localhost/audit"
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if proc.returncode != 0:
        return {
            "ok": False,
            "missing_columns": [],
            "error": f"alembic_offline_exit={proc.returncode}",
        }

    from db.models import Signal

    rendered = proc.stdout
    migrated: set[str] = set()
    create_match = re.search(r"CREATE TABLE signals \((.*?)\n\);", rendered, re.S | re.I)
    if create_match:
        for raw_line in create_match.group(1).splitlines():
            line = raw_line.strip().rstrip(",")
            if not line or line.upper().startswith((
                "PRIMARY KEY", "CONSTRAINT", "FOREIGN KEY", "UNIQUE", "CHECK"
            )):
                continue
            migrated.add(line.split()[0].strip('"').lower())
    for match in re.finditer(
        r"ALTER TABLE signals ADD COLUMN(?: IF NOT EXISTS)?\s+([A-Za-z_][A-Za-z0-9_]*)",
        rendered,
        re.I,
    ):
        migrated.add(match.group(1).lower())

    expected = {column.name.lower() for column in Signal.__table__.columns}
    missing = sorted(expected - migrated)
    guard_sql_present = bool(
        re.search(
            r"CREATE UNIQUE INDEX(?: IF NOT EXISTS)? ix_signals_active_thesis",
            rendered,
            re.I,
        )
    )
    return {
        "ok": not missing and guard_sql_present,
        "missing_columns": missing,
        "active_guard_sql": guard_sql_present,
    }


def audit_ml_rejected_runtime_contract(root: Path = ROOT) -> dict[str, object]:
    """Ensure the rendered chain contains every MLRejectedSignal ORM column."""
    env = os.environ.copy()
    env["DATABASE_MIGRATION_URL"] = "postgresql+psycopg2://audit:audit@localhost/audit"
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=root, env=env, text=True, capture_output=True, timeout=90, check=False,
    )
    if proc.returncode != 0:
        return {"ok": False, "missing_columns": [], "error": f"alembic_offline_exit={proc.returncode}"}
    from db.models import MLRejectedSignal
    rendered = proc.stdout
    migrated: set[str] = set()
    create_match = re.search(r"CREATE TABLE(?: IF NOT EXISTS)? ml_rejected_signals \((.*?)\n\s*\);", rendered, re.S | re.I)
    if create_match:
        for raw_line in create_match.group(1).splitlines():
            line = raw_line.strip().rstrip(",")
            if line and not line.upper().startswith(("PRIMARY KEY", "CONSTRAINT", "FOREIGN KEY", "UNIQUE", "CHECK")):
                migrated.add(line.split()[0].strip('"').lower())
    for match in re.finditer(
        r"ALTER TABLE ml_rejected_signals ADD COLUMN(?: IF NOT EXISTS)?\s+([A-Za-z_][A-Za-z0-9_]*)",
        rendered, re.I,
    ):
        migrated.add(match.group(1).lower())
    expected = {column.name.lower() for column in MLRejectedSignal.__table__.columns}
    missing = sorted(expected - migrated)
    return {"ok": not missing, "missing_columns": missing}



def audit_outcome_projection_contract(root: Path = ROOT) -> dict[str, object]:
    """Ensure one mutable Outcome projection is enforced per signal."""
    env = os.environ.copy()
    env["DATABASE_MIGRATION_URL"] = "postgresql+psycopg2://audit:audit@localhost/audit"
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=root, env=env, text=True, capture_output=True, timeout=90, check=False,
    )
    if proc.returncode != 0:
        return {"ok": False, "error": f"alembic_offline_exit={proc.returncode}"}
    rendered = proc.stdout
    unique_sql = bool(
        re.search(
            r"CREATE UNIQUE INDEX(?: IF NOT EXISTS)? uq_outcomes_signal_id\s+ON outcomes \(signal_id\)",
            rendered, re.I,
        )
    )
    from db.models import Outcome
    model_unique = any(
        getattr(constraint, "name", None) == "uq_outcomes_signal_id"
        for constraint in Outcome.__table__.constraints
    )
    return {
        "ok": bool(unique_sql and model_unique),
        "unique_guard_sql": unique_sql,
        "model_unique_constraint": model_unique,
    }

def audit_live_financial_contract(root: Path = ROOT) -> dict[str, object]:
    """Verify execution/payout tables and idempotency constraints exist in head."""
    migration = (root / "db/migrations/versions/0029_live_financial_ledger.py").read_text(encoding="utf-8", errors="replace")
    required_markers = (
        '"broker_executions"',
        '"payout_accounts"',
        '"payout_requests"',
        'uq_broker_execution_provider_key',
        'uq_payout_account_user_currency',
        'uq_payout_request_reference',
    )
    missing = [marker for marker in required_markers if marker not in migration]
    try:
        from db.models import BrokerExecution, PayoutAccountRecord, PayoutRequestRecord
        model_tables = {BrokerExecution.__tablename__, PayoutAccountRecord.__tablename__, PayoutRequestRecord.__tablename__}
    except Exception as exc:
        return {"ok": False, "missing": missing, "error": f"model_import:{type(exc).__name__}"}
    expected_tables = {"broker_executions", "payout_accounts", "payout_requests"}
    if model_tables != expected_tables:
        missing.extend(sorted(expected_tables - model_tables))
    return {"ok": not missing, "missing": missing}


def main() -> int:
    result = audit_versions()
    signal_contract = audit_signal_runtime_contract()
    rejected_contract = audit_ml_rejected_runtime_contract()
    outcome_contract = audit_outcome_projection_contract()
    financial_contract = audit_live_financial_contract()
    result["signal_runtime_contract"] = signal_contract
    result["ml_rejected_runtime_contract"] = rejected_contract
    result["outcome_projection_contract"] = outcome_contract
    result["live_financial_contract"] = financial_contract
    result["ok"] = bool(
        result["ok"]
        and signal_contract["ok"]
        and rejected_contract["ok"]
        and outcome_contract["ok"]
        and financial_contract["ok"]
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
