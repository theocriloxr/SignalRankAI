from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from services.continuous_improvement.weekly_review import run_weekly_review


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a recommendation-only SignalRankAI research review")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--external-openai", action="store_true", help="Opt in to aggregate-only OpenAI review")
    parser.add_argument("--output-dir", default="artifacts/continuous-improvement")
    args = parser.parse_args()
    report, paths = asyncio.run(
        run_weekly_review(
            days=max(1, args.days),
            request_external=bool(args.external_openai),
            output_dir=Path(args.output_dir),
        )
    )
    print(json.dumps({
        "ok": True,
        "review_id": report.review_id,
        "recommendations": len(report.recommendations),
        "incidents": len(report.incidents),
        "external_review_status": report.external_review_status,
        "artifacts": [str(path) for path in paths or ()],
        "production_mutation": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
