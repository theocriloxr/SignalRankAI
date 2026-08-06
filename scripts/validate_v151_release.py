#!/usr/bin/env python3
"""Deterministic local v1.5.1 release validation.

This certifies repository-level work only. It deliberately does not claim live
provider, Railway, Telegram, payment, app-store or legal certification.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(name: str, command: list[str]) -> dict[str, object]:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    return {
        "name": name,
        "command": command,
        "exit_code": result.returncode,
        "ok": result.returncode == 0,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def main() -> int:
    python = sys.executable
    steps = [
        ("compileall", [python, "-m", "compileall", "-q", "."]),
        ("alembic_heads", [python, "-m", "alembic", "heads"]),
        ("governance", [python, "scripts/build_v7_governance.py", "--check"]),
        ("secret_scan", [python, "scripts/secret_scan.py"]),
        (
            "complete_system",
            [
                python,
                "scripts/run_complete_system_test.py",
                "--full",
                "--pytest-batches",
                "20",
                "--continue-on-failure",
                "--output-dir",
                "artifacts/v151-local-complete",
            ],
        ),
    ]
    results = [run(name, command) for name, command in steps]
    report = {
        "release": "v1.5.1",
        "scope": "local_repository_certification",
        "all_passed": all(bool(item["ok"]) for item in results),
        "steps": results,
        "external_certification_required": True,
    }
    output = ROOT / "artifacts" / "v151_local_certification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"all_passed": report["all_passed"], "report": str(output)}, indent=2))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
