#!/usr/bin/env python3
"""Compile owned Python source without scanning virtual environments.

Prefer Git's tracked-file inventory when available. Railway source builds and
release ZIPs may not include ``.git`` metadata, so fall back to a deterministic
filesystem scan with the same deployable-source exclusions.
"""
from __future__ import annotations

import py_compile
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "node_modules",
    "artifacts",
    "evidence",
    "logs",
    ".diagnostics",
    ".pytest-tmp",
}


def _filesystem_python_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.py")
        if path.is_file()
        and not any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts)
    )


def tracked_python_files() -> list[Path]:
    try:
        output = subprocess.check_output(
            ["git", "ls-files", "*.py"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return _filesystem_python_files()

    files = [ROOT / line for line in output.splitlines() if line.strip()]
    existing = sorted(path for path in files if path.is_file())
    return existing or _filesystem_python_files()


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
