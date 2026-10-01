from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "release_certification_manifest.txt"


def test_release_certification_manifest_references_existing_tests() -> None:
    errors: list[str] = []
    for raw in MANIFEST.read_text(encoding="utf-8").splitlines():
        node = raw.strip()
        if not node or node.startswith("#"):
            continue
        path_text, *selectors = node.split("::")
        path = ROOT / path_text
        if not path.is_file():
            errors.append(f"missing test file: {path_text}")
            continue
        if not selectors:
            continue
        source = path.read_text(encoding="utf-8")
        test_name = selectors[0]
        pattern = re.compile(
            rf"(?m)^\s*(?:async\s+)?def\s+{re.escape(test_name)}\s*\("
        )
        if not pattern.search(source):
            errors.append(f"missing test selector: {node}")
    assert not errors, "\n".join(errors)
