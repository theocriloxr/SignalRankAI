"""CLI for the read-only public-testing release guard."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.release_guard import evaluate_release


def main() -> int:
    report = evaluate_release()
    print(json.dumps(report.as_dict(), sort_keys=True, default=str))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
