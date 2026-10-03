#!/usr/bin/env python3
"""Fail closed on findings, incomplete analysis, malformed evidence or tool failure."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = [
    "core",
    "engine",
    "web",
    "worker",
    "db",
    "data",
    "strategies",
    "services",
    "ml",
    "signalrank_telegram",
    "runtime",
    "execution",
    "railway_main.py",
    "frontend/src",
    "mobile",
]


def _build_command(output: Path, targets: list[str]) -> list[str]:
    executable = shutil.which("semgrep")
    if not executable:
        raise RuntimeError("semgrep executable is unavailable")
    return [
        executable,
        "scan",
        # Serial scans give each taint analysis the host's available CPU and
        # reduce memory pressure without excluding rules or scan targets.
        "--jobs",
        "1",
        "--error",
        "--strict",
        "--config",
        "p/default",
        "--config",
        "p/security-audit",
        "--metrics",
        "off",
        "--json",
        "--output",
        str(output),
        "--timeout",
        "30",
        "--timeout-threshold",
        "0",
        "--exclude=**/migrations/**",
        "--exclude=**/alembic/**",
        "--exclude-rule",
        "python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text",
        *targets,
    ]


def _validate_report(report: object, *, minimum_scanned: int, raw_exit: int = 0) -> dict[str, int]:
    if not isinstance(report, dict):
        raise RuntimeError("semgrep_report_not_object")

    results = report.get("results")
    errors = report.get("errors")
    paths = report.get("paths")
    if not isinstance(results, list):
        raise RuntimeError("semgrep_report_missing_results")
    if not isinstance(errors, list):
        raise RuntimeError("semgrep_report_missing_errors")

    scanned: list[object] = []
    if isinstance(paths, dict) and isinstance(paths.get("scanned"), list):
        scanned = list(paths["scanned"])

    if len(scanned) < int(minimum_scanned):
        raise RuntimeError(
            f"semgrep_scan_surface_too_small:{len(scanned)}<{int(minimum_scanned)}"
        )
    if errors:
        first = errors[0]
        raise RuntimeError(
            "semgrep_scan_errors:"
            + json.dumps(first, sort_keys=True, default=str)[:1200]
        )
    timing = report.get("time")
    if isinstance(timing, dict) and timing.get("fixpoint_timeouts"):
        raise RuntimeError("semgrep_incomplete_taint_analysis")
    if results:
        compact = [
            {
                "check_id": row.get("check_id"),
                "path": row.get("path"),
                "start": (row.get("start") or {}).get("line")
                if isinstance(row, dict)
                else None,
            }
            for row in results[:20]
            if isinstance(row, dict)
        ]
        raise RuntimeError(
            "semgrep_findings:"
            + json.dumps(compact, sort_keys=True, default=str)
        )
    if raw_exit != 0:
        raise RuntimeError(f"semgrep_nonzero_exit:{raw_exit}")
    return {"findings": 0, "errors": 0, "scanned": len(scanned)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minimum-scanned", type=int, default=400)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/security/semgrep.json")
    parser.add_argument("targets", nargs="*")
    args = parser.parse_args()
    targets = args.targets or list(DEFAULT_TARGETS)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="signalrank-semgrep-") as td:
        output = Path(td) / "semgrep.json"
        command = _build_command(output, targets)
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if completed.stdout:
            print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")

        if not output.is_file():
            print(
                f"SEMGREP_GATE_FAIL raw_exit={completed.returncode} reason=missing_json_report",
                file=sys.stderr,
            )
            return 2
        shutil.copyfile(output, args.output)
        try:
            report = json.loads(output.read_text(encoding="utf-8"))
            evidence = _validate_report(report, minimum_scanned=args.minimum_scanned, raw_exit=completed.returncode)
        except Exception as exc:
            print(
                f"SEMGREP_GATE_FAIL raw_exit={completed.returncode} reason={exc}",
                file=sys.stderr,
            )
            return 2

        print(
            "SEMGREP_GATE_PASS "
            + json.dumps(
                {
                    **evidence,
                    "raw_exit": int(completed.returncode),
                },
                sort_keys=True,
            )
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
