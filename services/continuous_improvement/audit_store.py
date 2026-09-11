from __future__ import annotations

import json
from pathlib import Path

from .recommendation_schema import ReviewReport


def write_review_artifacts(report: ReviewReport, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{report.review_id}.json"
    markdown_path = output_dir / f"{report.review_id}.md"
    json_path.write_text(json.dumps(report.as_dict(), indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    lines = [
        f"# SignalRankAI Continuous-Improvement Review {report.review_id}",
        "",
        f"Period: `{report.period_start}` to `{report.period_end}`",
        f"Code SHA: `{report.code_sha}`",
        f"Dataset SHA-256: `{report.dataset_hash}`",
        f"External review: `{report.external_review_status}`",
        "",
        "## Summary",
        "",
        "```json",
        json.dumps(report.summary, indent=2, sort_keys=True, default=str),
        "```",
        "",
        "## Recommendations",
        "",
    ]
    lines.extend(
        f"- `{item.recommendation_id}` [{item.kind.value}/{item.provider}] {item.title} — owner approval required"
        for item in report.recommendations
    )
    if not report.recommendations:
        lines.append("- No change recommended from available evidence.")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path
