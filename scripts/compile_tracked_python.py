#!/usr/bin/env python3
"""Compile every Git-tracked Python source file without scanning local venvs."""
from __future__ import annotations

import py_compile
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def tracked_python_files() -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "*.py"],
        cwd=ROOT,
        text=True,
    )
    return [ROOT / line for line in output.splitlines() if line.strip()]


def main() -> int:
    failures: list[str] = []
    files = tracked_python_files()
    for path in files:
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:
            failures.append(f"{path.relative_to(ROOT)}: {type(exc).__name__}: {exc}")
    print(f"tracked_python={len(files)} failures={len(failures)}")
    if failures:
        print("\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
