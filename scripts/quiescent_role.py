#!/usr/bin/env python3
"""Quiescent Railway role certification server.

Runs only after start.sh has passed release-source and database-schema admission.
It proves role identity and safety configuration without starting any SignalRank
engine, delivery, outcome, analytics, Telegram, scheduler, payment, payout, or
broker-execution loop.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import sys
import threading
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.financial_activation import force_invalid_financial_flags_off
from runtime.roles import RunMode, process_ownership

_ALLOWED_ROLES = {
    RunMode.FRONTDOOR,
    RunMode.WEB,
    RunMode.BOT,
    RunMode.ENGINE,
    RunMode.DELIVERY,
    RunMode.OUTCOME,
    RunMode.ANALYTICS,
    RunMode.SCHEDULER,
}
_HARD_OFF_FLAGS = (
    "LIVE_FINANCIAL_FEATURES_ENABLED",
    "REAL_EXECUTION_ENABLED",
    "AUTO_EXECUTION_ENABLED",
    "AUTO_TRADE_ENABLED",
    "COPY_TRADE_ENABLED",
    "MT5_ALLOW_LIVE_ACCOUNTS",
    "BYBIT_EXECUTION_ENABLED",
    "HYPERLIQUID_MAINNET_EXECUTION_ENABLED",
    "REAL_PAYOUTS_ENABLED",
    "AUTOMATIC_PAYOUTS_ENABLED",
    "PAYSTACK_TRANSFERS_ENABLED",
    "PAYMENTS_PUBLIC_ENABLED",
)


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def validate_quiescent_environment(
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    env = dict(os.environ if environ is None else environ)
    environment = str(
        env.get("RAILWAY_ENVIRONMENT_NAME")
        or env.get("RAILWAY_ENVIRONMENT")
        or env.get("APP_ENV")
        or ""
    ).strip().lower()
    profile = str(env.get("SIGNALRANK_ENV_PROFILE") or "").strip().lower()
    requested = str(
        env.get("RUN_MODE")
        or env.get("SERVICE_ROLE")
        or env.get("DB_ROLE")
        or ""
    ).strip().lower()

    if environment != "staging":
        raise RuntimeError(f"quiescent certification requires staging environment, got {environment or 'unknown'}")
    if profile != "staging-certification":
        raise RuntimeError(
            "quiescent certification requires SIGNALRANK_ENV_PROFILE=staging-certification"
        )

    ownership = process_ownership(requested, env)
    if ownership.mode not in _ALLOWED_ROLES:
        raise RuntimeError(
            f"quiescent certification forbids role={ownership.mode.value}"
        )
    if not _truthy(env.get("GLOBAL_EXECUTION_KILL_SWITCH")):
        raise RuntimeError("GLOBAL_EXECUTION_KILL_SWITCH must be enabled")

    enabled = [name for name in _HARD_OFF_FLAGS if _truthy(env.get(name))]
    if enabled:
        raise RuntimeError(
            "quiescent certification requires financial/execution flags off: "
            + ",".join(sorted(enabled))
        )

    if not _truthy(env.get("DATABASE_SCHEMA_GATE_ENABLED", "1")):
        raise RuntimeError("DATABASE_SCHEMA_GATE_ENABLED must remain enabled")
    if not _truthy(env.get("RELEASE_SOURCE_GATE_ENABLED", "1")):
        raise RuntimeError("RELEASE_SOURCE_GATE_ENABLED must remain enabled")

    return {
        "status": "PASS",
        "environment": environment,
        "profile": profile,
        "role": ownership.mode.value,
        "decomposed": bool(ownership.decomposed),
        "http_owned": bool(ownership.http),
        "telegram_owned": bool(ownership.telegram),
        "scheduler_owned": bool(ownership.scheduler),
        "engine_owned": bool(ownership.engine),
        "worker_owned": bool(ownership.worker),
        "execution_kill_switch": True,
        "financial_flags_off": list(_HARD_OFF_FLAGS),
        "release_commit": str(
            env.get("RAILWAY_GIT_COMMIT_SHA")
            or env.get("GIT_COMMIT_SHA")
            or ""
        )[:12],
    }


class _Handler(BaseHTTPRequestHandler):
    report: dict[str, object] = {}

    def do_GET(self) -> None:  # noqa: N802
        if self.path not in {"/", "/healthz", "/readyz"}:
            self.send_response(404)
            self.end_headers()
            return
        payload = json.dumps(self.report, sort_keys=True).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def main() -> int:
    forced = force_invalid_financial_flags_off(os.environ)
    if forced:
        print(
            "QUIESCENT_FORCED_FINANCIAL_FLAGS_OFF "
            + json.dumps({"flags": list(forced)}, sort_keys=True),
            flush=True,
        )

    report = validate_quiescent_environment(os.environ)
    _Handler.report = report
    print(
        "QUIESCENT_CERTIFICATION_PASS " + json.dumps(report, sort_keys=True),
        flush=True,
    )

    host = "0.0.0.0"
    port = int(os.getenv("PORT") or "8080")
    server = ThreadingHTTPServer((host, port), _Handler)
    stop = threading.Event()

    def _shutdown(*_: object) -> None:
        if stop.is_set():
            return
        stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    print(f"QUIESCENT_HTTP_LISTEN host={host} port={port}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
