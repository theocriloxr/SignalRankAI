#!/usr/bin/env python3
"""Synthetic 100k-recipient fanout-planning benchmark (no network sends)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from delivery.fanout import iter_delivery_batches


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=100_000)
    parser.add_argument("--shards", type=int, default=32)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-seconds", type=float, default=5.0)
    args = parser.parse_args()

    users = max(1, int(args.users))
    user_ids = range(1, users + 1)
    tracemalloc.start()
    started = time.perf_counter()
    batches = list(
        iter_delivery_batches(
            user_ids,
            shard_count=max(1, args.shards),
            batch_size=max(1, args.batch_size),
        )
    )
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    flattened = [uid for batch in batches for uid in batch.user_ids]
    result = {
        "users": users,
        "batches": len(batches),
        "shards": args.shards,
        "batch_size": args.batch_size,
        "elapsed_seconds": round(elapsed, 4),
        "peak_memory_mb": round(peak / 1024 / 1024, 2),
        "duplicates": len(flattened) - len(set(flattened)),
        "missing": users - len(set(flattened)),
        "network_delivery_simulated": False,
    }
    print(json.dumps(result, sort_keys=True))
    if result["duplicates"] or result["missing"] or elapsed > max(0.1, args.max_seconds):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
