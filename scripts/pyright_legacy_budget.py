#!/usr/bin/env python3
"""Fail if full-runtime Pyright debt grows beyond the certified baseline.

This is a transitional non-regression gate. Release-critical modules are checked
separately with zero tolerated errors via pyright-critical.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

BASELINE = int(os.getenv("PYRIGHT_LEGACY_ERROR_BUDGET", "1532"))
TARGETS = [
    "core", "engine", "web", "worker", "db", "data", "strategies", "services",
    "ml", "signalrank_telegram", "runtime", "execution", "railway_main.py", "config.py",
]


def main() -> int:
    proc = subprocess.run(
        ["pyright", "--outputjson", *TARGETS],
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout or "{}")
        summary = payload.get("summary") or {}
        errors = int(summary.get("errorCount") or 0)
        warnings = int(summary.get("warningCount") or 0)
    except Exception as exc:
        sys.stderr.write(proc.stdout[-4000:] if proc.stdout else "")
        sys.stderr.write(proc.stderr[-4000:] if proc.stderr else "")
        raise SystemExit(f"PYRIGHT_LEGACY_BUDGET_BLOCKED parse_error={type(exc).__name__}")

    print(
        f"PYRIGHT_LEGACY_BUDGET errors={errors} warnings={warnings} "
        f"baseline={BASELINE} delta={errors - BASELINE}"
    )
    if errors > BASELINE:
        raise SystemExit(
            f"PYRIGHT_LEGACY_BUDGET_BLOCKED errors={errors} baseline={BASELINE}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
