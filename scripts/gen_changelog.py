from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "CHANGELOG_AND_MANUAL_ACTIONS.md"
OUT = ROOT / "docs" / "CHANGELOG_SUMMARY.md"


def main() -> int:
    if not SRC.exists():
        OUT.write_text("# Changelog Summary\n\nNo changelog source found.\n", encoding="utf-8")
        return 0

    txt = SRC.read_text(encoding="utf-8")
    lines = txt.splitlines()
    top = lines[:80]
    content = [
        "# Changelog Summary",
        "",
        f"_Generated at {datetime.now(timezone.utc).isoformat()}_",
        "",
        "## Latest Snapshot",
        "",
        *top,
        "",
    ]
    OUT.write_text("\n".join(content), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
