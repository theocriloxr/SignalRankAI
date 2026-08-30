"""Create a conservative, evidence-backed soak verdict from JSON samples."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def evaluate(samples: list[dict], *, minimum_hours: int = 24) -> dict[str, object]:
    hours = max((float(item.get("hours", 0) or 0) for item in samples), default=0.0)
    safety_failures = [item.get("reason", "unknown") for item in samples if item.get("safety_ok") is False]
    duplicate_count = sum(int(item.get("duplicate_deliveries", 0) or 0) for item in samples)
    return {
        "soak_passed": bool(hours >= minimum_hours and not safety_failures and duplicate_count == 0),
        "hours_observed": hours,
        "minimum_hours": minimum_hours,
        "safety_failures": safety_failures,
        "duplicate_deliveries": duplicate_count,
        "launch_claim": "evidence only; not a profitability guarantee",
    }


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    samples = json.loads(path.read_text(encoding="utf-8")) if path else []
    result = evaluate(list(samples or []))
    print(json.dumps(result, sort_keys=True))
    return 0 if result["soak_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
