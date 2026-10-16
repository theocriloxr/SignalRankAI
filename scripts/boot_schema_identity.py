"""Prefix read-only migration diagnostics without shell pipelines or sed."""
from __future__ import annotations

import subprocess
import sys


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"heads", "current"}:
        return 64
    command = sys.argv[1]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", command],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False,
    )
    label = "expected_head" if command == "heads" else "current"
    for line in result.stdout.splitlines():
        print(f"[boot] alembic_{label}={line}", flush=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
