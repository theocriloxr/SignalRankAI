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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
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


def _build_command(output: Path, targets: list[str], engine: str = "semgrep") -> list[str]:
    if engine not in {"semgrep", "opengrep"}:
        raise RuntimeError("unsupported SAST engine")
    executable = shutil.which(engine)
    if not executable:
        raise RuntimeError(f"{engine} executable is unavailable")
    if engine == "opengrep":
        from scripts.install_opengrep import verify_binary
        verify_binary(Path(executable))
    command = [
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
    if engine == "semgrep":
        command[2:2] = ["--metrics", "off"]
    return command


def _validate_probe(report: object, raw_exit: int) -> None:
    if not isinstance(report, dict) or raw_exit != 1:
        raise RuntimeError("sast_probe_did_not_reject_unsafe_code")
    if report.get("errors") != [] or (report.get("time") or {}).get("fixpoint_timeouts"):
        raise RuntimeError("sast_probe_incomplete")
    results = report.get("results")
    if not isinstance(results, list) or len((report.get("paths") or {}).get("scanned", [])) != 3:
        raise RuntimeError("sast_probe_missing_evidence")
    required = {
        ("python.boto3.security.hardcoded-token.hardcoded-token", "unsafe_sample.py"),
        ("python.flask.security.injection.user-eval.eval-injection", "unsafe_sample.py"),
        ("javascript.lang.security.detect-eval-with-expression.detect-eval-with-expression", "unsafe_sample.ts"),
    }
    observed = {(row["check_id"], Path(row["path"]).name) for row in results}
    if not required <= observed or any(name == "safe_sample.py" for _, name in observed):
        raise RuntimeError("sast_probe_detection_regression")


def _run_engine_probe(directory: Path, engine: str, evidence: Path) -> None:
    fixtures = directory / "fixtures"
    fixtures.mkdir()
    # Static fixtures are scanned, never imported or executed. The token is fabricated.
    (fixtures / "unsafe_sample.py").write_text('''import boto3
from flask import Flask, request
app = Flask(__name__)
def hardcoded():
    return boto3.client("s3", aws_secret_access_key="TestOnlyAbC19eF47GhJ28KmN35PqR62StU89VwX01")
@app.route("/unsafe")
def unsafe():
    command = request.args.get("expression")
    return eval(command)
''', encoding="utf-8")
    (fixtures / "unsafe_sample.ts").write_text(
        "const code = window.location.hash;\neval(code);\n", encoding="utf-8")
    (fixtures / "safe_sample.py").write_text('''import os
import boto3
def configured():
    return boto3.client("s3", aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"])
''', encoding="utf-8")
    output = directory / "probe.json"
    command = _build_command(output, [str(fixtures)], engine)
    command[2:2] = ["--no-git-ignore", "--no-rewrite-rule-ids"]
    completed = subprocess.run(command, cwd=ROOT, text=True, encoding="utf-8",
                               errors="replace", stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, check=False, timeout=300)
    if not output.is_file():
        raise RuntimeError("sast_probe_missing_report")
    shutil.copyfile(output, evidence)
    _validate_probe(json.loads(output.read_text(encoding="utf-8")), completed.returncode)


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
    parser.add_argument("--engine", choices=["semgrep", "opengrep"], default="opengrep")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/security/semgrep.json")
    parser.add_argument("targets", nargs="*")
    args = parser.parse_args()
    targets = args.targets or list(DEFAULT_TARGETS)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="signalrank-semgrep-") as td:
        if args.engine == "opengrep":
            try:
                _run_engine_probe(Path(td), args.engine, args.output.with_suffix(".probe.json"))
            except Exception as exc:
                print(f"SEMGREP_GATE_FAIL engine={args.engine} reason={exc}", file=sys.stderr)
                return 2
        output = Path(td) / "semgrep.json"
        command = _build_command(output, targets, args.engine)
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
                    "engine": args.engine,
                },
                sort_keys=True,
            )
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
