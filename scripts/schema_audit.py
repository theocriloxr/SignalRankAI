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

def main() -> int:
    result = audit_versions()
    signal_contract = audit_signal_runtime_contract()
    result["signal_runtime_contract"] = signal_contract
    result["ok"] = bool(result["ok"] and signal_contract["ok"])
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
