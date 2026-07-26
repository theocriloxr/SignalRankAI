#!/usr/bin/env python3
"""Run the complete local SignalRankAI verification orchestration.

This is one reproducible command that combines static architecture checks,
schema/environment/provider contracts, and the broad hermetic integration
suite.  It deliberately labels local/mock evidence separately from live
Railway/Telegram/provider certification.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]


@dataclass(slots=True)
class StepResult:
    name: str
    command: list[str]
    ok: bool
    exit_code: int
    duration_seconds: float
    log_path: str
    attempts: int = 1


HERMETIC_TEST_FILES = (
    "tests/test_railway_lifecycle.py",
    "tests/test_railway_redis_queue.py",
    "tests/test_redis_webhook_queue.py",
    "tests/test_command_contracts.py",
    "tests/test_command_tier_contract.py",
    "tests/test_callback_handler.py",
    "tests/test_dispatch_update_smoke.py",
    "tests/test_trader_profiles_and_platform_reliability.py",
    "tests/test_indices_asset_support.py",
    "tests/test_connectors.py",
    "tests/test_connectors_providers.py",
    "tests/test_provider_catalog_and_certification.py",
    "tests/test_provider_registry_fail_closed.py",
    "tests/test_delivery_fanout_planner.py",
    "tests/test_delivery_freshness.py",
    "tests/test_signal_delivery_ack.py",
    "tests/test_outcome_delivery_contract.py",
    "tests/test_outcome_integration_multi_tp.py",
    "tests/test_outcome_provenance_hardening.py",
    "tests/test_paper_ledger_exits.py",
    "tests/test_paystack_webhook.py",
    "tests/test_broker_execution_p0.py",
    "tests/test_execution_safety.py",
    "tests/test_native_mt5_bridge_hardening.py",
    "tests/test_mt5_signal_router_queue.py",
    "tests/test_smart_dca_hardening.py",
    "tests/test_tiered_execution_canonical_routing.py",
    "tests/test_resource_governor.py",
    "tests/test_runtime_config_snapshot.py",
    "tests/test_engine_critical_fallbacks_fail_closed.py",
    "tests/test_engine_final_safety_gates.py",
    "tests/test_asset_repeat_policy.py",
    "tests/test_extended_provider_adapters.py",
    "tests/test_web_api_tokens.py",
    "tests/test_env_examples_no_duplicates.py",
    "tests/test_post_deploy_smoke_contract.py",
    "tests/test_railway_simulation_contract.py",
    "tests/test_live_production_evidence.py",
)


def _run_step(
    name: str,
    command: Sequence[str],
    output_dir: Path,
    env: dict[str, str],
    *,
    max_attempts: int = 1,
) -> StepResult:
    """Run one verification step with bounded process-group cleanup.

    A few optional integration tests create descendant processes/threads that
    can outlive a pytest interpreter on constrained container platforms. Each
    attempt therefore runs in its own process group. A timed-out group is
    terminated without blocking the orchestrator, and pytest batches may be
    retried once in a fresh interpreter. A step is successful only when an
    actual attempt exits with status zero.
    """
    log_path = output_dir / f"{name}.log"
    started = time.monotonic()
    timeout_seconds = int(env.get("COMPLETE_SYSTEM_STEP_TIMEOUT_SECONDS", "300") or 300)
    command_text = "COMMAND: " + shlex.join(command) + "\n"
    log_path.write_text(command_text, encoding="utf-8")
    exit_code = 1
    attempts_used = 0

    for attempt in range(1, max(1, max_attempts) + 1):
        attempts_used = attempt
        with log_path.open("a", encoding="utf-8") as log_handle:
            log_handle.write(f"\nATTEMPT {attempt}/{max(1, max_attempts)}\n\n")
            log_handle.flush()
            process: subprocess.Popen[str] | None = None
            try:
                process = subprocess.Popen(
                    list(command),
                    cwd=ROOT,
                    env=env,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                    start_new_session=True,
                )
                deadline = time.monotonic() + max(30, timeout_seconds)
                while process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.1)
                if process.poll() is None:
                    exit_code = 124
                    log_handle.write(f"\nTIMEOUT after {timeout_seconds}s; terminating process group\n")
                    log_handle.flush()
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        log_handle.write("PROCESS_GROUP_DID_NOT_REAP_WITHIN_5S\n")
                else:
                    exit_code = int(process.returncode or 0)
            except Exception as exc:
                exit_code = 1
                log_handle.write(f"\nORCHESTRATOR_ERROR type={type(exc).__name__}\n")
                if process is not None and process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
        if exit_code == 0:
            break
        if attempt < max_attempts:
            with log_path.open("a", encoding="utf-8") as log_handle:
                log_handle.write("\nRETRYING_IN_FRESH_PROCESS\n")

    return StepResult(
        name=name,
        command=list(command),
        ok=exit_code == 0,
        exit_code=exit_code,
        duration_seconds=round(time.monotonic() - started, 3),
        log_path=str(log_path.relative_to(ROOT) if log_path.is_relative_to(ROOT) else log_path),
        attempts=attempts_used,
    )


def _partition_pytest_files(batch_count: int) -> list[list[str]]:
    """Partition the complete test-file inventory into deterministic batches.

    Some optional libraries and integration tests create background resources
    that can keep a monolithic pytest interpreter alive after the final test on
    constrained CI/container platforms.  Running the *entire inventory* in
    bounded, deterministic file batches preserves complete coverage while also
    isolating teardown and making a hung file group diagnosable.
    """
    files = [str(path.relative_to(ROOT)) for path in sorted((ROOT / "tests").rglob("test_*.py"))]
    if not files:
        return []
    requested = int(batch_count or 0)
    count = len(files) if requested <= 0 else max(1, min(requested, len(files)))
    # Contiguous chunks preserve the repository's canonical lexical test order.
    chunk_size = (len(files) + count - 1) // count
    return [files[index:index + chunk_size] for index in range(0, len(files), chunk_size)]


def build_steps(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    python = sys.executable
    env_paths = [
        ".env.example",
        "RAILWAY_ENV_UPDATED.env.example",
        *[str(path.relative_to(ROOT)) for path in sorted((ROOT / "configs" / "env").glob("*.env.example"))],
        *[str(path.relative_to(ROOT)) for path in sorted((ROOT / "deploy" / "railway_roles").glob("*.env"))],
    ]
    steps: list[tuple[str, list[str]]] = [
        ("compileall", [python, "-m", "compileall", "-q", "."]),
        ("env_contracts", [python, "scripts/validate_env_contract.py", *env_paths]),
        ("schema_audit", [python, "scripts/schema_audit.py"]),
        ("architecture_smoke", [python, "scripts/architecture_smoke.py"]),
        ("db_session_audit", [python, "scripts/audit_db_session_calls.py"]),
        ("governance_validation", [python, "scripts/validate_governance_docs.py"]),
        ("secret_scan", [python, "scripts/secret_scan.py"]),
        ("production_readiness", [python, "scripts/production_readiness_check.py"]),
        (
            "runtime_config",
            [
                python,
                "scripts/runtime_config_snapshot.py",
                "--profile",
                args.profile,
                "--output",
                str(Path(args.output_dir) / "runtime_config_snapshot.json"),
            ],
        ),
        (
            "railway_simulation",
            [python, "scripts/simulate_railway.py", "--port", str(getattr(args, "simulation_port", 8877))],
        ),
        (
            "fanout_load",
            [
                python,
                "scripts/load_test_delivery_planner.py",
                "--users",
                "100000",
                "--shards",
                "32",
                "--batch-size",
                "100",
                "--max-seconds",
                "10",
            ],
        ),
        (
            "provider_certification",
            [
                python,
                "scripts/certify_providers.py",
                *( ["--live"] if args.live_providers else [] ),
                "--output-dir",
                str(Path(args.output_dir) / "provider-certification"),
            ],
        ),
    ]
    if args.full:
        requested_batches = int(getattr(args, "pytest_batches", 20) or 0)
        if requested_batches == 1:
            # Pytest discovery has cleaner teardown than passing the entire
            # repository as one extremely long explicit argv on some Railway
            # and container runtimes. It still covers every test_*.py file.
            steps.append((
                "full_pytest_batch_01",
                [python, "-m", "pytest", "-q"],
            ))
        else:
            # Run every test file, but isolate teardown into deterministic batches.
            batches = _partition_pytest_files(requested_batches)
            for index, files in enumerate(batches, start=1):
                steps.append((
                    f"full_pytest_batch_{index:02d}",
                    [python, "-m", "pytest", "-q", *files],
                ))
    else:
        steps.append((
            "hermetic_system_suite",
            [python, "-m", "pytest", "-q", *HERMETIC_TEST_FILES],
        ))
    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="artifacts/complete-system-test")
    parser.add_argument("--profile", default="configs/env/railway-hobby-owner-beta.env.example")
    parser.add_argument("--full", action="store_true", help="run every test file in deterministic bounded batches")
    parser.add_argument(
        "--pytest-batches",
        type=int,
        default=20,
        help="number of deterministic pytest file batches; 0 isolates every test file",
    )
    parser.add_argument("--live-providers", action="store_true", help="perform opt-in external provider calls")
    parser.add_argument("--continue-on-failure", action="store_true")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="resume from passed steps recorded in the output directory",
    )
    parser.add_argument("--simulation-port", type=int, default=8877)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env.setdefault("SIGNALRANK_DISABLE_BACKGROUND_THREADS", "1")
    expected_steps = build_steps(args)
    progress_path = output_dir / "complete_system_test_progress.json"
    results: list[StepResult] = []
    if args.resume and progress_path.exists():
        try:
            payload = json.loads(progress_path.read_text(encoding="utf-8"))
            results = [StepResult(**item) for item in payload.get("steps", [])]
        except (OSError, ValueError, TypeError):
            results = []
    passed_names = {result.name for result in results if result.ok}

    def save_progress() -> None:
        progress_path.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "profile": args.profile,
                    "full_suite_requested": args.full,
                    "pytest_batches": args.pytest_batches,
                    "steps": [asdict(result) for result in results],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    for name, command in expected_steps:
        if name in passed_names:
            print(f"SKIP {name} (already passed in resume state)", flush=True)
            continue
        # Replace a previously failed attempt for the same named step.
        results = [result for result in results if result.name != name]
        result = _run_step(
            name,
            command,
            output_dir,
            env,
            max_attempts=2 if name.startswith("full_pytest_batch_") else 1,
        )
        results.append(result)
        save_progress()
        print(
            f"{'PASS' if result.ok else 'FAIL'} {name} "
            f"({result.duration_seconds:.3f}s) -> {result.log_path}",
            flush=True,
        )
        if not result.ok and not args.continue_on_failure:
            break

    expected_names = [name for name, _ in expected_steps]
    result_by_name = {result.name: result for result in results}
    ordered_results = [result_by_name[name] for name in expected_names if name in result_by_name]
    results = ordered_results
    report = {
        "evidence_scope": "LOCAL_WITH_LIVE_PROVIDER_CALLS" if args.live_providers else "HERMETIC_LOCAL_ONLY",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": args.profile,
        "full_suite_requested": args.full,
        "live_provider_calls_requested": args.live_providers,
        "ok": bool(results) and all(result.ok for result in results) and len(results) == len(expected_steps),
        "steps": [asdict(result) for result in results],
        "not_proven_by_this_command": [
            "Railway deployment",
            "Telegram network delivery",
            "PostgreSQL/PgBouncer live connection",
            "two live Redis services",
            "Paystack test transaction",
            "TradingView external alert",
            "MetaApi demo order",
            "24-72 hour soak",
        ],
    }
    save_progress()
    report_path = output_dir / "complete_system_test_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"overall={'PASS' if report['ok'] else 'FAIL'} report={report_path}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
