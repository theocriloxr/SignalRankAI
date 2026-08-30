"""Deterministic capacity sanity check for event and user partitioning.

This is not a production load test. It catches pathological partition choices
before a Redis/Railway load test and emits machine-readable distribution data.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from statistics import mean, pstdev

from core.durable_event_stream import DurableEventStream


def simulate(users: int, partitions: int, alerts_per_user: int) -> dict:
    stream = DurableEventStream(partitions=partitions, enabled=False)
    counts = Counter()
    for user_id in range(1, users + 1):
        partition = stream.partition_for(f"user:{user_id}")
        counts[partition] += alerts_per_user
    values = [counts[i] for i in range(partitions)]
    avg = mean(values)
    maximum = max(values)
    minimum = min(values)
    return {
        "users": users,
        "partitions": partitions,
        "alerts_per_user": alerts_per_user,
        "total_events": sum(values),
        "mean_events_per_partition": avg,
        "min_events_per_partition": minimum,
        "max_events_per_partition": maximum,
        "max_to_mean_ratio": maximum / avg if avg else 0.0,
        "coefficient_of_variation": pstdev(values) / avg if avg else 0.0,
        "recommended_min_partitions_by_250k_events": max(1, math.ceil(sum(values) / 250000)),
        "distribution": {str(i): counts[i] for i in range(partitions)},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=100000)
    parser.add_argument("--partitions", type=int, default=32)
    parser.add_argument("--alerts-per-user", type=int, default=20)
    parser.add_argument("--max-imbalance", type=float, default=1.10)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    result = simulate(max(1, args.users), max(1, args.partitions), max(1, args.alerts_per_user))
    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if result["max_to_mean_ratio"] > args.max_imbalance:
        raise SystemExit(
            f"partition imbalance {result['max_to_mean_ratio']:.4f} exceeds {args.max_imbalance:.4f}"
        )


if __name__ == "__main__":
    main()
