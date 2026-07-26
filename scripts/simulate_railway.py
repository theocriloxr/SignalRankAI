#!/usr/bin/env python3
"""Run a bounded local simulation of Railway's monolith startup contract.

The simulation deliberately disables real integrations and money movement. It
starts the actual ``railway_main:app`` through uvicorn, verifies liveness and
webhook ingress, captures logs, and terminates cleanly.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def _load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json"}
    request_headers.update(headers or {})
    req = Request(url, data=data, method=method, headers=request_headers)
    with urlopen(req, timeout=3) as response:  # nosec - localhost simulation only
        raw = response.read().decode("utf-8")
        return int(response.status), json.loads(raw or "{}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8877)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument(
        "--env-file",
        default=str(ROOT / "configs/env/hermetic-test.env.example"),
    )
    args = parser.parse_args()

    env = os.environ.copy()
    env.update(_load_env(Path(args.env_file)))
    env.update(
        {
            "PYTHONPATH": os.pathsep.join(
                part
                for part in (
                    os.getenv("SIGNALRANK_TEST_PYDEPS", "").strip(),
                    str(ROOT),
                    env.get("PYTHONPATH", ""),
                )
                if part
            ),
            "PORT": str(args.port),
            "RAILWAY_SERVICE_NAME": "signalrank-local-simulation",
            "RAILWAY_ENVIRONMENT": "simulation",
            "RAILWAY_ENVIRONMENT_NAME": "simulation",
            # A no-dependency simulation verifies the exact web/lifespan route
            # contract while preventing access to real external systems.
            "DATABASE_URL": "",
            "REDIS_URL": "",
            "DELIVERY_REDIS_URL": "",
            "STATE_REDIS_URL": "",
            "TELEGRAM_BOT_TOKEN": "",
            "WEBHOOK_DOMAIN": "",
            "RUN_ENGINE_LOOP": "0",
            "RUN_WORKER_LOOP": "0",
            "WEBHOOK_REDIS_QUEUE_ENABLED": "0",
            "WEBHOOK_UPDATE_WORKERS": "4",
            "WEBHOOK_UPDATE_QUEUE_SIZE": "100",
            "ENABLE_NEWS": "0",
            "ENABLE_ML": "0",
            "AUTO_MIGRATE": "0",
            "RUN_DB_MIGRATIONS_AT_BOOT": "false",
            "AUTO_TRADE_ENABLED": "0",
            "COPY_TRADE_ENABLED": "0",
            "REAL_PAYOUTS_ENABLED": "0",
            "PAYMENTS_PUBLIC_ENABLED": "0",
        }
    )

    command = [sys.executable, "-m", "uvicorn", "railway_main:app", "--host", "127.0.0.1", "--port", str(args.port)]
    proc = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    logs: list[str] = []
    base = f"http://127.0.0.1:{args.port}"
    deadline = time.monotonic() + max(5.0, args.timeout)
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            try:
                status, health = _json_request(base + "/healthz")
                if status == 200:
                    break
            except (URLError, ConnectionError, TimeoutError, ValueError):
                time.sleep(0.25)
        else:
            raise RuntimeError("Railway simulation did not become healthy before timeout")

        status, health = _json_request(base + "/healthz")
        if status != 200 or health.get("status") not in {"ok", "healthy", "degraded"}:
            raise RuntimeError(f"unexpected health response: {status} {health}")

        status, webhook = _json_request(
            base + "/telegram/webhook",
            method="POST",
            payload={"update_id": 999001, "message": {"message_id": 1, "chat": {"id": 100001}, "text": "/start"}},
            headers={
                "X-Telegram-Bot-Api-Secret-Token": str(env.get("TELEGRAM_WEBHOOK_SECRET") or "")
            },
        )
        if status != 200 or webhook.get("ok") is not True or webhook.get("queued") is not True:
            raise RuntimeError(f"webhook ingress contract failed: {status} {webhook}")

        print("[railway_simulation] health=PASS")
        print(f"[railway_simulation] webhook=PASS backend={webhook.get('queue_backend')}")
        print("[railway_simulation] real_integrations=DISABLED")
        return 0
    finally:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except Exception:
            proc.terminate()
        try:
            output, _ = proc.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                proc.kill()
            output, _ = proc.communicate(timeout=5)
        logs.extend((output or "").splitlines())
        log_path = ROOT / ".pytest-tmp" / "railway-simulation.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(logs) + "\n", encoding="utf-8")
        print(f"[railway_simulation] log={log_path}")


if __name__ == "__main__":
    raise SystemExit(main())
