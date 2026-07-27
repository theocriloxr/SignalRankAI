"""Read-only migration-chain audit used by the release guard."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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


def main() -> int:
    result = audit_versions()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
