#!/usr/bin/env python3
"""Run lease contracts against an owned loopback Redis, never production.

Requires redis-server; missing binaries fail this explicit integration gate.
No connection to a configured application Redis or database is inherited.
This proves the scoped lease contracts, not failover or financial readiness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.assert_release_source import validate_release_source
from scripts.generate_release_provenance import release_identity


def tested_source_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for name in ("core/redis_state.py", "engine/signal_lock.py", "engine/dedup_wrapper.py",
                 "engine/core.py", "db/pg_features.py", "signalrank_telegram/delivery_cooldown.py",
                 "tests/test_signal_lease_ownership.py", "scripts/certify_signal_leases.py", "requirements.lock"):
        digest.update(name.encode() + b"\0" + hashlib.sha256((root / name).read_bytes()).digest())
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    binary = shutil.which("redis-server")
    if not binary:
        raise SystemExit("SIGNAL_LEASE_INTEGRATION_BLOCKED redis-server unavailable")
    env = {key: value for key, value in os.environ.items() if key.upper() in {
        "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC", "HOME", "USERPROFILE",
    }}
    env.update(APP_ENV="test", ENVIRONMENT="test", SIGNALRANK_ALLOW_DOTENV="0",
               SIGNALRANK_DISABLE_BACKGROUND_THREADS="1", GLOBAL_EXECUTION_KILL_SWITCH="1",
               REAL_EXECUTION_ENABLED="0", AUTO_EXECUTION_ENABLED="0", AUTO_TRADE_ENABLED="0",
               COPY_TRADE_ENABLED="0", PROP_EXECUTION_ENABLED="0", REAL_PAYOUTS_ENABLED="0",
               PYTHONPATH=str(root), PYTHONUTF8="1")
    if validate_release_source():
        raise SystemExit("SIGNAL_LEASE_INTEGRATION_BLOCKED release identity mismatch")
    sha, branch = release_identity()
    source_hash = tested_source_hash(root)
    version = subprocess.check_output([binary, "--version"], env=env, text=True).strip()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    if port == 6379:
        raise SystemExit("SIGNAL_LEASE_INTEGRATION_BLOCKED unsafe test port")
    report = {"commit": sha, "branch": branch, "tested_source_sha256": source_hash,
              "redis_version": version, "mode": "isolated_loopback_redis",
              "production_connections": False, "financial_readiness_certified": False}
    with tempfile.TemporaryDirectory(prefix="signalrank-redis-leases-") as directory:
        with open(Path(directory) / "redis.log", "w", encoding="utf-8") as output:
            process = subprocess.Popen(
                [binary, "--bind", "127.0.0.1", "--port", str(port), "--save", "", "--appendonly", "no",
                 "--dir", directory, "--protected-mode", "yes"],
                env=env, stdout=output, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            try:
                import redis
                url = f"redis://127.0.0.1:{port}/0"
                client = redis.from_url(url, socket_timeout=1, socket_connect_timeout=1)
                deadline = time.monotonic() + 10
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("owned Redis exited before ready")
                    try:
                        if client.ping():
                            break
                    except redis.exceptions.RedisError:
                        if time.monotonic() >= deadline:
                            raise RuntimeError("owned Redis readiness timed out") from None
                    time.sleep(0.05)
                client.close()
                env["SIGNALRANK_LEASE_TEST_REDIS_URL"] = url
                result = subprocess.run(
                    [sys.executable, "scripts/pytest_hard_exit.py", "-q", "tests/test_signal_lease_ownership.py",
                     "--basetemp", str(Path(directory) / "pytest"), "--junitxml", str(Path(directory) / "tests.xml")],
                    cwd=root, env=env, check=False,
                )
                report["exit_code"] = result.returncode
                report["status"] = "PASS" if result.returncode == 0 else "FAILED"
                report["source_unchanged"] = source_hash == tested_source_hash(root) and (sha, branch) == release_identity()
                args.output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(Path(directory) / "tests.xml", args.output.with_suffix(".xml"))
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                report["owned_redis_stopped"] = process.poll() is not None
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("SIGNAL_LEASE_INTEGRATION " + json.dumps(report, sort_keys=True))
    return 0 if report.get("status") == "PASS" and report.get("source_unchanged") and report.get("owned_redis_stopped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
