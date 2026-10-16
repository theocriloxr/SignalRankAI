"""Run local checks in a credential-free environment against an owned test DB.

No inherited service credentials, broker destinations, or production URLs reach
the child. Reports describe local evidence only and retain failure exit codes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SAFE_ENV = {"SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP", "USERPROFILE",
            "APPDATA", "LOCALAPPDATA", "COMSPEC", "PROGRAMFILES", "PROGRAMFILES(X86)",
            "PROGRAMDATA", "HOMEDRIVE", "HOMEPATH"}


def test_environment() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k.upper() in SAFE_ENV}
    env.update(APP_ENV="test", ENVIRONMENT="test", SIGNALRANK_ALLOW_DOTENV="0", SIGNALRANK_DISABLE_BACKGROUND_THREADS="1",
               DATABASE_URL="postgresql+asyncpg://stage1_test@127.0.0.1:55434/signalrank_stage1_test",
               DATABASE_MIGRATION_URL="postgresql://stage1_test@127.0.0.1:55434/signalrank_stage1_test",
               SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED="1", GLOBAL_EXECUTION_KILL_SWITCH="1",
               PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONPATH=str(ROOT),
               PLAYWRIGHT_BROWSERS_PATH=str(ROOT / ".pytest-tmp/stage1-browsers"),
               PYTEST_ADDOPTS="-o cache_dir=.pytest-tmp/stage1-cache --basetemp=.pytest-tmp/stage1-pytest",
               EXPECTED_ALEMBIC_HEAD="0055_user_renewal_default")
    for flag in ("REAL_EXECUTION_ENABLED", "AUTO_EXECUTION_ENABLED", "AUTO_TRADE_ENABLED", "COPY_TRADE_ENABLED",
                 "PROP_EXECUTION_ENABLED", "REAL_PAYOUTS_ENABLED", "LIVE_FINANCIAL_FEATURES_ENABLED",
                 "MT5_ALLOW_LIVE_ACCOUNTS", "MT5_LIVE_EXECUTION_ENABLED", "MT5_AUTO_EXECUTION_ENABLED",
                 "BYBIT_EXECUTION_ENABLED", "HYPERLIQUID_MAINNET_EXECUTION_ENABLED", "AUTOMATIC_PAYOUTS_ENABLED"):
        env[flag] = "0"
    return env


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--step-timeout-seconds", type=int)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.command or not args.name.replace("-", "").replace("_", "").isalnum():
        parser.error("a safe check name and command are required")
    command = args.command[1:] if args.command[0] == "--" else args.command
    if command[0] == "python": command[0] = sys.executable
    cwd = (ROOT / args.cwd).resolve()
    if not cwd.is_relative_to(ROOT): parser.error("working directory must stay in this workspace")
    directory = ROOT / "artifacts/stage1-20261014"
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / (args.name + ".log")
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    def source_fingerprint():
        paths = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, text=True).splitlines()
        entries = []
        for name in sorted(set(paths)):
            path = ROOT / name
            if not path.is_file() or name.startswith(("docs/", "artifacts/")):
                continue
            entries.append((name, hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()))
        return hashlib.sha256(json.dumps(entries).encode()).hexdigest()
    before = source_fingerprint()
    started = datetime.now(timezone.utc).isoformat()
    env = test_environment()
    if args.step_timeout_seconds is not None:
        if not 30 <= args.step_timeout_seconds <= 3600:
            parser.error("step timeout must be between 30 and 3600 seconds")
        env["COMPLETE_SYSTEM_STEP_TIMEOUT_SECONDS"] = str(args.step_timeout_seconds)
    env["PYTEST_ADDOPTS"] = f"-o cache_dir=.pytest-tmp/stage1-cache-{args.name} --basetemp=.pytest-tmp/stage1-pytest-{args.name}"
    with log.open("wb") as output:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
    receipt = {"name": args.name, "sha": sha, "environment": "isolated_local_postgresql17",
               "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
               "command": command, "cwd": args.cwd, "exit_code": result.returncode,
               "step_timeout_seconds": args.step_timeout_seconds,
               "log": log.relative_to(ROOT).as_posix(), "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
               "result": "PASS" if result.returncode == 0 else "FAIL",
               "source_fingerprint_before": before, "source_fingerprint_after": source_fingerprint(),
               "scope": "Local check only; no hosted CI, deployment, provider, broker or live execution certification"}
    (directory / (args.name + ".json")).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt))
    print(log.read_text("utf-8", errors="replace")[-5000:])
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
