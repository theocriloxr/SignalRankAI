"""Create a conservative, evidence-backed soak verdict from JSON samples."""

from __future__ import annotations

import json
import sys
import math
import re
from datetime import datetime, timezone
from pathlib import Path


IDENTITY_FIELDS = ("release_sha", "source_sha256", "schema_head", "configuration_sha256", "environment_id", "deployment_ids")
COUNTERS = ("duplicate_deliveries", "duplicate_orders", "unhandled_errors")


def evaluate(samples: list[dict], *, minimum_hours: int = 24,
             now: datetime | None = None) -> dict[str, object]:
    """Validate trusted monitor observations, never a caller's claimed hours.

    Counters describe each observation interval, not lifetime cumulative totals.
    Reviewers must still establish monitor provenance against retained raw logs.
    This report cannot certify other release gates or authenticate its inputs.
    """
    current = now or datetime.now(timezone.utc)
    failures: list[str] = []
    times: list[float] = []
    totals = {name: 0 for name in COUNTERS}
    identity: dict[str, object] | None = None
    if type(minimum_hours) is not int or not 24 <= minimum_hours <= 72:
        failures.append("minimum_window_must_be_24_to_72_hours")
    if not isinstance(samples, list) or len(samples) < 2:
        failures.append("insufficient_monitor_observations")
        samples = []
    for index, item in enumerate(samples):
        prefix = f"sample_{index}:"
        if not isinstance(item, dict):
            failures.append(prefix + "invalid_observation")
            continue
        observed_identity = {key: item.get(key) for key in IDENTITY_FIELDS}
        valid_identity = (
            all(observed_identity.values())
            and re.fullmatch(r"[0-9a-f]{40}", str(item.get("release_sha", "")))
            and all(re.fullmatch(r"[0-9a-f]{64}", str(item.get(key, "")))
                    for key in ("source_sha256", "configuration_sha256"))
            and isinstance(item.get("deployment_ids"), dict)
            and all(isinstance(key, str) and key and isinstance(value, str) and value
                    for key, value in (item.get("deployment_ids") or {}).items())
        )
        if not valid_identity:
            failures.append(prefix + "missing_or_invalid_release_identity")
        if identity is None:
            identity = observed_identity
        elif observed_identity != identity:
            failures.append(prefix + "release_or_deployment_changed")
        try:
            stamp = datetime.fromisoformat(str(item.get("observed_at", "")).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("timezone_required")
            seconds = stamp.timestamp()
            if not math.isfinite(seconds) or seconds > current.timestamp() + 5:
                raise ValueError("invalid_or_future_timestamp")
            times.append(seconds)
        except (ValueError, OverflowError, OSError):
            failures.append(prefix + "invalid_observation_timestamp")
        for key in ("safety_ok", "readiness_ok"):
            if item.get(key) is not True:
                failures.append(prefix + key + "_not_proven")
        for key in COUNTERS:
            value = item.get(key)
            if type(value) is not int or value < 0:
                failures.append(prefix + key + "_missing_or_invalid")
            else:
                totals[key] += value
                if value:
                    failures.append(prefix + key)
    hours = (times[-1] - times[0]) / 3600 if len(times) > 1 else 0.0
    if any(not 0 < later - earlier <= 300 for earlier, later in zip(times, times[1:])):
        failures.append("monitor_gap_or_non_monotonic_timestamps")
    if times and current.timestamp() - times[-1] > 300:
        failures.append("monitor_evidence_stale")
    if hours < minimum_hours:
        failures.append("insufficient_observed_duration")
    return {
        "soak_passed": not failures,
        "hours_observed": hours,
        "minimum_hours": minimum_hours,
        "sample_count": len(samples),
        "maximum_sample_gap_seconds": 300,
        "safety_failures": failures,
        **totals,
        "release_identity": identity,
        "launch_claim": "trusted monitor evidence only; other release gates and input provenance require independent review",
    }


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    try:
        samples = json.loads(path.read_text(encoding="utf-8")) if path else []
        result = evaluate(samples)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"soak_passed": False, "error": type(exc).__name__}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["soak_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
