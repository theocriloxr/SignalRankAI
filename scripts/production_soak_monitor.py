"""Read-only monitoring of a fixed production release; never financial certification.

Railway variable values are hashed in memory and are never written to evidence.
The local monitor must stay running. Missing samples remain gaps, not backfilled
observations. Database duplicate counters and deployed source bytes are explicitly
unverified, so availability monitoring alone cannot pass the release soak gate.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import urlopen

TRUTHY = {"1", "true", "yes", "on", "y"}
FINANCIAL_FLAGS = (
    "LIVE_FINANCIAL_FEATURES_ENABLED", "REAL_EXECUTION_ENABLED", "AUTO_EXECUTION_ENABLED",
    "AUTO_TRADE_ENABLED", "COPY_TRADE_ENABLED", "PROP_EXECUTION_ENABLED", "REAL_PAYOUTS_ENABLED",
    "MT5_LIVE_EXECUTION_ENABLED", "MT5_AUTO_EXECUTION_ENABLED", "BYBIT_EXECUTION_ENABLED",
    "HYPERLIQUID_MAINNET_EXECUTION_ENABLED",
)
VOLATILE_METADATA = {
    "RAILWAY_DEPLOYMENT_ID", "RAILWAY_SNAPSHOT_ID", "RAILWAY_GIT_COMMIT_SHA",
    "RAILWAY_GIT_COMMIT_MESSAGE", "RAILWAY_GIT_AUTHOR", "RAILWAY_GIT_BRANCH",
}


def evaluate_observation(config: dict, health: dict, services: dict) -> dict:
    failures = []
    identity = health.get("release_identity") or {}
    release_ok = (
        identity.get("confirmed") is True
        and identity.get("deployed_git_sha") == config["release_sha"]
        and identity.get("expected_git_sha") == config["release_sha"]
        and identity.get("deployed_alembic_revision") == config["schema_head"]
        and identity.get("expected_alembic_revision") == config["schema_head"]
    )
    if not release_ok:
        failures.append("public_release_identity_mismatch")
    if health.get("status") != "ready" or health.get("ready") is not True:
        failures.append("public_readiness_not_proven")
    financial = (health.get("checks") or {}).get("financial_activation") or {}
    if not (financial.get("ok") is True and financial.get("requested") is False
            and financial.get("live_execution_requested") is False and financial.get("payouts_requested") is False):
        failures.append("public_financial_safety_not_proven")
    summaries, configuration = {}, {}
    for role, expected in config["services"].items():
        observed = services.get(role) or {}
        variables = observed.get("variables")
        active = [row for row in observed.get("deployments", []) if row.get("status") == "SUCCESS"]
        exact = [row for row in active if row.get("id") == expected["deployment_id"]]
        if len(active) != 1 or len(exact) != 1:
            failures.append(role + ":active_deployment_changed_or_missing")
        deployment_sha = ((exact[0].get("meta") or {}).get("commitHash")) if exact else None
        if deployment_sha != config["release_sha"]:
            failures.append(role + ":deployment_source_mismatch")
        if not isinstance(variables, dict):
            failures.append(role + ":configuration_unavailable")
            summaries[role] = {"deployment_id": expected["deployment_id"], "status": "unverified"}
            continue
        configuration[role] = {key: value for key, value in variables.items() if key not in VOLATILE_METADATA}
        flags_off = all(str(variables.get(key, "0")).strip().lower() not in TRUTHY for key in FINANCIAL_FLAGS)
        kill_on = str(variables.get("GLOBAL_EXECUTION_KILL_SWITCH", "")).strip().lower() in TRUTHY
        pin_ok = variables.get("EXPECTED_RELEASE_COMMIT") == config["release_sha"]
        if not (flags_off and kill_on and pin_ok):
            failures.append(role + ":configuration_safety_not_proven")
        summaries[role] = {"deployment_id": expected["deployment_id"], "status": "SUCCESS" if exact else "unverified",
                           "source_matches": deployment_sha == config["release_sha"], "financial_flags_off": flags_off,
                           "kill_switch_on": kill_on, "approval_pin_matches": pin_ok}
    return {"readiness_ok": not failures, "safety_ok": not failures,
            "failures": failures, "services": summaries,
            "configuration_sha256": hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
            if len(configuration) == len(config["services"]) else None}


def summarize(samples: list[dict], config: dict, *, now: datetime) -> dict:
    times = [datetime.fromisoformat(item["observed_at"]).timestamp() for item in samples]
    hours = (times[-1] - times[0]) / 3600 if len(times) > 1 else 0.0
    gaps = [later - earlier for earlier, later in zip(times, times[1:])]
    configs = {item.get("configuration_sha256") for item in samples}
    healthy = bool(samples) and all(item.get("readiness_ok") is True for item in samples)
    continuous = bool(times) and all(0 < value <= 300 for value in gaps) and 0 <= now.timestamp() - times[-1] <= 300
    stable = len(configs) == 1 and None not in configs
    return {"status": "MONITORING" if healthy and continuous and stable else "DEGRADED",
            "observed_hours": hours, "target_hours": config["hours"], "sample_count": len(samples),
            "maximum_gap_seconds": max(gaps, default=0), "configuration_stable": stable,
            "availability_window_24h_passed": hours >= 24 and healthy and continuous and stable,
            "target_availability_window_passed": hours >= config["hours"] and healthy and continuous and stable,
            "release_soak_certified": False, "financial_readiness_certified": False,
            "release_sha": config["release_sha"], "schema_head": config["schema_head"],
            "environment_id": config["environment_id"],
            "unverified": ["deployed_source_bytes", "duplicate_delivery_intervals", "duplicate_order_intervals",
                           "complete_runtime_error_intervals", "broker_fills_and_reconciliation", "final_launch_candidate"],
            "latest_failures": samples[-1].get("failures", []) if samples else ["no_observations"]}


def _cli_json(config: dict, command: list[str]) -> object:
    result = subprocess.run([config["railway_cli"], *command], capture_output=True, text=True,
                            timeout=25, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError("railway_read_failed")
    return json.loads(result.stdout)


def collect(config: dict) -> dict:
    with urlopen(config["base_url"].rstrip("/") + "/readyz", timeout=25) as response:
        if response.status != 200:
            raise RuntimeError("readiness_http_failure")
        health = json.load(response)
    def role_read(item: tuple[str, dict]) -> tuple[str, dict]:
        role, service = item
        common = ["--project", config["project_id"], "--environment", config["environment_id"], "--service", service["service_id"], "--json"]
        deployments = _cli_json(config, ["deployment", "list", *common, "--limit", "50"])
        variables = _cli_json(config, ["variable", "list", *common])
        if not isinstance(deployments, list) or not isinstance(variables, dict):
            raise RuntimeError("railway_read_shape_invalid")
        return role, {"deployments": deployments, "variables": variables}
    with ThreadPoolExecutor(max_workers=4) as pool:
        services = dict(pool.map(role_read, config["services"].items()))
    # Only the filtered verdict escapes this function; raw variable maps remain
    # in memory and never enter stdout, logs, observations or exceptions.
    return evaluate_observation(config, health, services)


def _write(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if type(config.get("hours")) is not int or not 24 <= config["hours"] <= 72:
        raise ValueError("monitor_requires_24_to_72_hour_target")
    if type(config.get("interval_seconds")) is not int or not 30 <= config["interval_seconds"] <= 180:
        raise ValueError("monitor_interval_must_leave_room_for_read_timeouts")
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    observations = output / "observations.jsonl"
    if observations.exists() and not args.once:
        raise RuntimeError("existing_monitor_evidence_requires_a_new_run_directory")
    samples: list[dict] = []
    monitor_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    started = time.monotonic()
    _write(output / "process.json", {"pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat(),
                                    "monitor_source_sha256": monitor_hash, "config": config})
    while True:
        cycle_started = time.monotonic()
        try:
            sample = collect(config)
        except Exception as exc:
            sample = {"readiness_ok": False, "safety_ok": False, "configuration_sha256": None,
                      "failures": ["monitor_read_failed:" + type(exc).__name__]}
        observed = datetime.now(timezone.utc)
        sample.update(observed_at=observed.isoformat(), release_sha=config["release_sha"],
                      schema_head=config["schema_head"], environment_id=config["environment_id"],
                      monitor_source_sha256=monitor_hash)
        samples.append(sample)
        with observations.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sample, sort_keys=True) + "\n")
        result = summarize(samples, config, now=observed)
        result.update(updated_at=observed.isoformat(), elapsed_process_hours=(time.monotonic() - started) / 3600)
        _write(output / "status.json", result)
        print(json.dumps({key: result[key] for key in ("status", "observed_hours", "sample_count", "latest_failures")}), flush=True)
        if args.once:
            return 0 if sample.get("readiness_ok") is True else 1
        if result["observed_hours"] >= config["hours"]:
            return 0 if result["target_availability_window_passed"] is True else 1
        time.sleep(max(0.0, config["interval_seconds"] - (time.monotonic() - cycle_started)))


if __name__ == "__main__":
    raise SystemExit(main())
