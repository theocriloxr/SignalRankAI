from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .audit_store import write_review_artifacts
from .collector import collect_weekly_snapshot
from .recommendation_schema import ReviewReport
from .reviewer import review_snapshot


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def detect_incidents(snapshot: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    summary = dict(snapshot.get("summary") or {})
    deliveries = dict(snapshot.get("deliveries") or {})
    incidents: list[dict[str, Any]] = []
    if int(summary.get("signals") or 0) > 0 and int(deliveries.get("reserved") or 0) == 0:
        incidents.append({"code": "INC-SIGNAL-STORAGE", "severity": "high", "reason": "signals_without_delivery_reservations"})
    if int(deliveries.get("reserved") or 0) > 0 and int(deliveries.get("sent_ok") or 0) == 0:
        incidents.append({"code": "INC-DELIVERY", "severity": "high", "reason": "reservations_without_confirmed_delivery"})
    return tuple(incidents)


async def run_weekly_review(
    *,
    days: int = 7,
    request_external: bool = False,
    output_dir: Path | None = None,
) -> tuple[ReviewReport, tuple[Path, Path] | None]:
    collected = await collect_weekly_snapshot(days)
    snapshot = dict(collected["snapshot"])
    reviewed = await review_snapshot(snapshot, request_external=request_external)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=max(1, int(days)))
    identity = json.dumps([start.date().isoformat(), end.date().isoformat(), collected["dataset_hash"], _git_sha()])
    report = ReviewReport(
        review_id="review-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16],
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        code_sha=_git_sha(),
        dataset_hash=str(collected["dataset_hash"]),
        summary=snapshot,
        recommendations=tuple(reviewed["recommendations"]),
        incidents=detect_incidents(snapshot),
        external_review_status=str(reviewed["external_status"]),
    )
    paths = write_review_artifacts(report, output_dir) if output_dir else None
    return report, paths
