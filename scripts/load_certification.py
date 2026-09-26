"""Authorized distributed load-certification harness for SignalRankAI.

This script can:
1. build a deterministic sharded load plan from requirements/scale_profiles.yaml;
2. execute one HTTP load shard against an explicitly authorized target;
3. merge shard reports;
4. certify the merged load result only when companion runtime metrics satisfy
   every SLO declared by the selected scale profile.

It deliberately does not infer queue/database/delivery correctness from HTTP
latency. Those metrics must be supplied from the real staging observability
surface before a profile can PASS.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import json
import math
from pathlib import Path
import statistics
import time
from typing import Any, Iterable
from urllib.parse import urlparse

import httpx
import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILES = ROOT / "requirements" / "scale_profiles.yaml"


@dataclass(frozen=True, slots=True)
class LoadPlan:
    profile: str
    registered_users: int
    total_concurrency: int
    shards: int
    shard_index: int
    shard_concurrency: int
    duration_seconds: int
    base_url: str
    paths: tuple[str, ...]


def _ceil_share(total: int, shards: int, index: int) -> int:
    base, remainder = divmod(max(0, int(total)), max(1, int(shards)))
    return base + (1 if int(index) < remainder else 0)


def load_profiles(path: Path = DEFAULT_PROFILES) -> dict[str, dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    profiles = payload.get("profiles") or {}
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("scale_profiles_missing")
    return {str(name): dict(value or {}) for name, value in profiles.items()}


def build_plan(
    *,
    profile: str,
    base_url: str,
    paths: Iterable[str],
    shards: int,
    shard_index: int,
    duration_seconds: int | None = None,
    profiles_path: Path = DEFAULT_PROFILES,
) -> LoadPlan:
    profiles = load_profiles(profiles_path)
    if profile not in profiles:
        raise ValueError(f"unknown_scale_profile:{profile}")
    spec = profiles[profile]

    parsed = urlparse(str(base_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("load_target_must_be_absolute_http_url")

    shard_count = int(shards)
    index = int(shard_index)
    if shard_count < 1:
        raise ValueError("shards_must_be_positive")
    if index < 0 or index >= shard_count:
        raise ValueError("invalid_shard_index")

    normalized_paths = tuple(
        path if str(path).startswith("/") else f"/{path}"
        for path in [str(value).strip() for value in paths]
        if path
    )
    if not normalized_paths:
        raise ValueError("at_least_one_path_required")

    total_concurrency = int(spec.get("concurrent_users") or 0)
    if total_concurrency < 1:
        raise ValueError("profile_concurrency_missing")

    duration = int(duration_seconds or max(60, int(spec.get("required_soak_hours") or 1) * 60))
    if duration < 10:
        raise ValueError("duration_too_short")

    return LoadPlan(
        profile=profile,
        registered_users=int(spec.get("registered_users") or 0),
        total_concurrency=total_concurrency,
        shards=shard_count,
        shard_index=index,
        shard_concurrency=_ceil_share(total_concurrency, shard_count, index),
        duration_seconds=duration,
        base_url=f"{parsed.scheme}://{parsed.netloc}",
        paths=normalized_paths,
    )


def percentile(values: Iterable[float], q: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if not 0 < float(q) <= 1:
        raise ValueError("percentile_out_of_range")
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * float(q)) - 1))
    return ordered[index]


async def _worker(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    paths: tuple[str, ...],
    stop_at: float,
    worker_id: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    latencies: list[float] = []
    status_counts: dict[str, int] = {}
    errors = 0
    requests = 0
    cursor = worker_id % len(paths)
    while time.monotonic() < stop_at:
        path = paths[cursor % len(paths)]
        cursor += 1
        started = time.perf_counter()
        try:
            response = await client.get(
                f"{base_url}{path}",
                timeout=timeout_seconds,
                headers={"x-signalrank-load-probe": "authorized-certification"},
            )
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            latencies.append(elapsed_ms)
            requests += 1
            key = str(int(response.status_code))
            status_counts[key] = status_counts.get(key, 0) + 1
            if response.status_code >= 500:
                errors += 1
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            latencies.append(elapsed_ms)
            requests += 1
            errors += 1
            status_counts["exception"] = status_counts.get("exception", 0) + 1
    return {
        "requests": requests,
        "errors": errors,
        "latencies_ms": latencies,
        "status_counts": status_counts,
    }


async def execute_shard(
    plan: LoadPlan,
    *,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    if plan.shard_concurrency < 1:
        return {
            "schema_version": 1,
            "kind": "signalrank_load_shard",
            "plan": plan.__dict__,
            "requests": 0,
            "errors": 0,
            "duration_seconds": 0.0,
            "throughput_rps": 0.0,
            "latency_ms": {"p50": None, "p95": None, "p99": None, "max": None},
            "status_counts": {},
        }

    limits = httpx.Limits(
        max_connections=max(10, plan.shard_concurrency),
        max_keepalive_connections=max(10, min(plan.shard_concurrency, 5000)),
    )
    started = time.monotonic()
    stop_at = started + plan.duration_seconds
    async with httpx.AsyncClient(limits=limits, follow_redirects=False) as client:
        results = await asyncio.gather(
            *[
                _worker(
                    client,
                    base_url=plan.base_url,
                    paths=plan.paths,
                    stop_at=stop_at,
                    worker_id=index,
                    timeout_seconds=timeout_seconds,
                )
                for index in range(plan.shard_concurrency)
            ]
        )

    duration = max(0.001, time.monotonic() - started)
    latencies = [value for result in results for value in result["latencies_ms"]]
    requests = sum(int(result["requests"]) for result in results)
    errors = sum(int(result["errors"]) for result in results)
    status_counts: dict[str, int] = {}
    for result in results:
        for key, value in result["status_counts"].items():
            status_counts[key] = status_counts.get(key, 0) + int(value)

    return {
        "schema_version": 1,
        "kind": "signalrank_load_shard",
        "profile": plan.profile,
        "shards": plan.shards,
        "shard_index": plan.shard_index,
        "target": plan.base_url,
        "paths": list(plan.paths),
        "configured_total_concurrency": plan.total_concurrency,
        "shard_concurrency": plan.shard_concurrency,
        "requests": requests,
        "errors": errors,
        "error_rate": errors / requests if requests else 0.0,
        "duration_seconds": duration,
        "throughput_rps": requests / duration,
        "latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "max": max(latencies) if latencies else None,
        },
        "status_counts": status_counts,
    }


def merge_shard_reports(reports: Iterable[dict[str, Any]]) -> dict[str, Any]:
    reports = list(reports)
    if not reports:
        raise ValueError("no_shard_reports")

    profiles = {str(report.get("profile") or "") for report in reports}
    targets = {str(report.get("target") or "") for report in reports}
    shard_counts = {int(report.get("shards") or 0) for report in reports}
    indices = [int(report.get("shard_index") or -1) for report in reports]
    if len(profiles) != 1 or len(targets) != 1 or len(shard_counts) != 1:
        raise ValueError("incompatible_shard_reports")
    expected = next(iter(shard_counts))
    if expected < 1 or sorted(indices) != list(range(expected)):
        raise ValueError("incomplete_or_duplicate_shard_set")

    requests = sum(int(report.get("requests") or 0) for report in reports)
    errors = sum(int(report.get("errors") or 0) for report in reports)
    duration = max(float(report.get("duration_seconds") or 0) for report in reports)
    throughput = sum(float(report.get("throughput_rps") or 0) for report in reports)

    # Exact global percentiles require raw samples or histograms. Each shard
    # reports conservative maxima of shard percentiles so certification cannot
    # understate the worst observed shard.
    def worst(metric: str) -> float | None:
        values = [
            float(report.get("latency_ms", {}).get(metric))
            for report in reports
            if report.get("latency_ms", {}).get(metric) is not None
        ]
        return max(values) if values else None

    statuses: dict[str, int] = {}
    for report in reports:
        for key, value in dict(report.get("status_counts") or {}).items():
            statuses[key] = statuses.get(key, 0) + int(value)

    return {
        "schema_version": 1,
        "kind": "signalrank_load_merged",
        "profile": next(iter(profiles)),
        "target": next(iter(targets)),
        "shards": expected,
        "configured_total_concurrency": max(
            int(report.get("configured_total_concurrency") or 0)
            for report in reports
        ),
        "requests": requests,
        "errors": errors,
        "error_rate": errors / requests if requests else 0.0,
        "duration_seconds": duration,
        "throughput_rps": throughput,
        "latency_ms": {
            "p50_worst_shard": worst("p50"),
            "p95_worst_shard": worst("p95"),
            "p99_worst_shard": worst("p99"),
            "max": worst("max"),
        },
        "status_counts": statuses,
    }


def evaluate_certification(
    merged: dict[str, Any],
    metrics: dict[str, Any],
    *,
    profiles_path: Path = DEFAULT_PROFILES,
) -> dict[str, Any]:
    profile = str(merged.get("profile") or "")
    profiles = load_profiles(profiles_path)
    if profile not in profiles:
        raise ValueError(f"unknown_scale_profile:{profile}")
    spec = profiles[profile]
    required_slos = dict(spec.get("slos") or {})

    results: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    failed: list[str] = []

    for name, expected in required_slos.items():
        if name not in metrics:
            missing.append(name)
            continue
        actual = metrics[name]
        if name.endswith("_max") or name.startswith("duplicate_"):
            passed = float(actual) <= float(expected)
        elif name.endswith("_min"):
            passed = float(actual) >= float(expected)
        elif name.endswith("_ms") or name.endswith("_seconds"):
            passed = float(actual) <= float(expected)
        else:
            raise ValueError(f"unknown_slo_comparison:{name}")
        results[name] = {
            "actual": actual,
            "expected": expected,
            "passed": bool(passed),
        }
        if not passed:
            failed.append(name)

    concurrency_ok = (
        int(merged.get("configured_total_concurrency") or 0)
        >= int(spec.get("concurrent_users") or 0)
    )
    if not concurrency_ok:
        failed.append("configured_total_concurrency")

    status = "PASS" if not missing and not failed else "BLOCKED"
    return {
        "schema_version": 1,
        "kind": "signalrank_scale_certification",
        "profile": profile,
        "status": status,
        "concurrency": {
            "actual": int(merged.get("configured_total_concurrency") or 0),
            "required": int(spec.get("concurrent_users") or 0),
            "passed": concurrency_ok,
        },
        "load_summary": merged,
        "slo_results": results,
        "missing_slos": sorted(missing),
        "failed_slos": sorted(set(failed)),
        "claim_allowed": status == "PASS",
    }


def _read_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    plan_cmd = sub.add_parser("plan")
    plan_cmd.add_argument("--profile", default="large_scale")
    plan_cmd.add_argument("--base-url", required=True)
    plan_cmd.add_argument("--path", action="append", default=["/healthz"])
    plan_cmd.add_argument("--shards", type=int, default=1)
    plan_cmd.add_argument("--shard-index", type=int, default=0)
    plan_cmd.add_argument("--duration-seconds", type=int)

    run_cmd = sub.add_parser("run")
    run_cmd.add_argument("--profile", default="large_scale")
    run_cmd.add_argument("--base-url", required=True)
    run_cmd.add_argument("--path", action="append", default=["/healthz"])
    run_cmd.add_argument("--shards", type=int, default=1)
    run_cmd.add_argument("--shard-index", type=int, required=True)
    run_cmd.add_argument("--duration-seconds", type=int)
    run_cmd.add_argument("--timeout-seconds", type=float, default=10.0)
    run_cmd.add_argument("--output", required=True)
    run_cmd.add_argument("--acknowledge-authorized-target", action="store_true")

    merge_cmd = sub.add_parser("merge")
    merge_cmd.add_argument("reports", nargs="+")
    merge_cmd.add_argument("--output", required=True)

    cert_cmd = sub.add_parser("certify")
    cert_cmd.add_argument("--merged-report", required=True)
    cert_cmd.add_argument("--metrics-json", required=True)
    cert_cmd.add_argument("--output", required=True)

    args = parser.parse_args()

    if args.command in {"plan", "run"}:
        plan = build_plan(
            profile=args.profile,
            base_url=args.base_url,
            paths=args.path,
            shards=args.shards,
            shard_index=args.shard_index,
            duration_seconds=args.duration_seconds,
        )
        if args.command == "plan":
            print(json.dumps(plan.__dict__, sort_keys=True, indent=2))
            return 0
        if not args.acknowledge_authorized_target:
            raise SystemExit("load_run_requires_--acknowledge-authorized-target")
        report = asyncio.run(
            execute_shard(plan, timeout_seconds=float(args.timeout_seconds))
        )
        Path(args.output).write_text(
            json.dumps(report, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return 0

    if args.command == "merge":
        report = merge_shard_reports(_read_json(path) for path in args.reports)
        Path(args.output).write_text(
            json.dumps(report, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return 0

    merged = _read_json(args.merged_report)
    metrics = _read_json(args.metrics_json)
    result = evaluate_certification(merged, metrics)
    Path(args.output).write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": result["status"], "claim_allowed": result["claim_allowed"]}))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
