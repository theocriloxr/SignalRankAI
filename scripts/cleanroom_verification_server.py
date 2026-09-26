"""Isolated Railway clean-room verifier with a stateful health gate.

The HTTP listener binds immediately so Railway can distinguish "verification is
still running" from "process never started". /healthz returns 503 until every
configured compile/schema/test gate passes, then returns 200. Any failed gate
stays 503 with a non-secret failure summary available on /.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

if str(os.getenv("SIGNALRANK_CLEANROOM") or "").strip() != "1":
    raise SystemExit("cleanroom_verifier_requires_SIGNALRANK_CLEANROOM=1")

_TESTS = [
    "tests/test_multi_account_prop_policy.py",
    "tests/test_trading_account_ledger.py",
    "tests/test_broker_account_bola_idor.py",
    "tests/test_broker_credential_envelope.py",
    "tests/test_broker_credential_inventory.py",
    "tests/test_broker_execution_p0.py",
    "tests/test_canonical_broker_entrypoints.py",
    "tests/test_auth_fail_closed_boundaries.py",
    "tests/test_blueprint_certification_safety.py",
    "tests/test_quiescent_role_certification.py",
    "tests/test_ml_champion_challenger_governance.py",
    "tests/test_ml_registry.py",
    "tests/test_adaptive_dataset_and_wfo.py",
    "tests/test_delivery_fanout_planner.py",
    "tests/test_phase4_pass3_delivery_reliability.py",
    "tests/test_execution_state_machine.py",
    "tests/test_final_cross_channel_parity_20260925.py",
    "tests/test_v105_railway_readiness_hotfix.py",
    "tests/test_v106_delivery_db_hotfix.py",
    "tests/test_deployment_schema_completion_v151.py",
    "tests/test_production_endgame_20260725.py",
    "tests/test_v131_live_financial_activation.py",
    "tests/test_v130_production_cutover_outcome_recovery.py",
    "tests/test_mt5_reconciliation_ledger.py",
    "tests/test_web_first_signup_contract.py",
    "tests/test_release_provenance.py",
    "tests/test_traceability_completion_boundary.py",
    "tests/test_load_certification.py",
    "tests/test_copy_trade_safety_foundation.py",
]

_STEPS: list[tuple[str, list[str]]] = [
    (
        "compile",
        [
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "core",
            "db",
            "services",
            "web",
            "signalrank_telegram",
            "execution",
            "scripts",
            "tools",
            "worker",
            "railway_main.py",
        ],
    ),
    (
        "alembic_release_chain",
        [sys.executable, "scripts/verify_0045_release_chain.py"],
    ),
    (
        "schema_audit",
        [sys.executable, "scripts/schema_audit.py"],
    ),
    (
        "release_provenance",
        [
            sys.executable,
            "scripts/generate_release_provenance.py",
            "--output-dir",
            "/tmp/signalrank-release-provenance",
            "--verify-self",
        ],
    ),
    (
        "targeted_pytest",
        [sys.executable, "-m", "pytest", "-q", *_TESTS],
    ),
]

_state_lock = threading.Lock()
_state: dict[str, Any] = {
    "status": "RUNNING",
    "stage": "starting",
    "started_at_epoch": time.time(),
    "finished_at_epoch": None,
    "failed_stage": None,
    "exit_code": None,
}


def _set_state(**updates: Any) -> None:
    with _state_lock:
        _state.update(updates)


def _snapshot() -> dict[str, Any]:
    with _state_lock:
        result = dict(_state)
    result["commit"] = str(
        os.getenv("RAILWAY_GIT_COMMIT_SHA")
        or os.getenv("GIT_COMMIT_SHA")
        or ""
    )
    result["elapsed_seconds"] = round(
        max(0.0, time.time() - float(result["started_at_epoch"])), 3
    )
    return result


def _run_step(name: str, command: list[str]) -> int:
    _set_state(stage=name)
    print(
        "CLEANROOM_STAGE_START "
        + json.dumps({"stage": name, "command": command}, sort_keys=True),
        flush=True,
    )
    proc = subprocess.Popen(
        command,
        cwd=ROOT,
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        print(f"[{name}] {line.rstrip()}", flush=True)
    return_code = int(proc.wait())
    print(
        "CLEANROOM_STAGE_END "
        + json.dumps(
            {"stage": name, "exit_code": return_code},
            sort_keys=True,
        ),
        flush=True,
    )
    return return_code


def _verify() -> None:
    try:
        for name, command in _STEPS:
            exit_code = _run_step(name, command)
            if exit_code != 0:
                _set_state(
                    status="FAILED",
                    stage=name,
                    failed_stage=name,
                    exit_code=exit_code,
                    finished_at_epoch=time.time(),
                )
                return
        _set_state(
            status="PASS",
            stage="complete",
            failed_stage=None,
            exit_code=0,
            finished_at_epoch=time.time(),
        )
        print(
            "CLEANROOM_PASS "
            + json.dumps(
                {
                    "commit": _snapshot()["commit"],
                    "tests": len(_TESTS),
                },
                sort_keys=True,
            ),
            flush=True,
        )
    except BaseException as exc:
        _set_state(
            status="FAILED",
            failed_stage=str(_snapshot().get("stage") or "unknown"),
            exit_code=1,
            finished_at_epoch=time.time(),
        )
        print(
            "CLEANROOM_EXCEPTION "
            + json.dumps(
                {
                    "stage": _snapshot().get("stage"),
                    "type": type(exc).__name__,
                    "message": str(exc)[:500],
                },
                sort_keys=True,
            ),
            flush=True,
        )


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path not in {"/", "/healthz"}:
            self.send_response(404)
            self.end_headers()
            return

        state = _snapshot()
        if self.path == "/healthz":
            ok = state.get("status") == "PASS"
            payload = json.dumps(
                {
                    "status": state.get("status"),
                    "stage": state.get("stage"),
                    "commit": state.get("commit"),
                },
                sort_keys=True,
            ).encode("utf-8")
            self.send_response(200 if ok else 503)
        else:
            payload = json.dumps(state, sort_keys=True).encode("utf-8")
            self.send_response(200)

        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


threading.Thread(target=_verify, name="cleanroom-verifier", daemon=True).start()

port = int(os.getenv("PORT") or "8080")
print(
    "CLEANROOM_HTTP_LISTEN "
    + json.dumps({"host": "0.0.0.0", "port": port}, sort_keys=True),
    flush=True,
)
ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
