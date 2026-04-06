from __future__ import annotations

import re
from pathlib import Path


def test_db_migration_revision_ids_fit_alembic_version_column() -> None:
    versions_dir = (
        Path(__file__).resolve().parents[1] / "db" / "migrations" / "versions"
    )
    revision_re = re.compile(r'^\s*revision\s*=\s*"([^"]+)"\s*$')

    overlong: list[tuple[str, str, int]] = []
    for path in sorted(versions_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        match = None
        for line in text.splitlines():
            match = revision_re.match(line)
            if match:
                break
        if not match:
            continue
        rev = match.group(1)
        if len(rev) > 32:
            overlong.append((path.name, rev, len(rev)))

    assert not overlong, f"Migration revision IDs exceed 32 chars: {overlong}"
