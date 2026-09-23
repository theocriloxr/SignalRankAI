from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .audit_store import write_review_artifacts
from .collector import collect_weekly_snapshot
from .recommendation_schema import ReviewReport
from .reviewer import review_snapshot

logger = logging.getLogger(__name__)


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


async def _persist_latest_review(report: ReviewReport) -> None:
    """Persist the anonymized review so container replacement does not erase learning lineage."""
    try:
        from sqlalchemy import text

        from db.session import get_session, is_db_configured

        if not is_db_configured():
            return
        async with get_session() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO runtime_state(key, value, expires_at, updated_at)
                    VALUES ('continuous_improvement_last_review', CAST(:value AS JSONB), NULL, NOW())
                    ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
                    """
                ),
                {"value": json.dumps(report.as_dict(), default=str)},
            )
            await session.commit()
    except Exception:
        logger.warning("[continuous_improvement] latest review persistence failed", exc_info=True)


async def run_weekly_review(
    *,
    days: int = 7,
    request_external: bool = False,
    request_gemini: bool = False,
    output_dir: Path | None = None,
) -> tuple[ReviewReport, tuple[Path, Path] | None]:
    collected = await collect_weekly_snapshot(days)
    snapshot = dict(collected["snapshot"])
    if str(os.getenv("FULL_MARKET_LEARNING_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}:
        profile = snapshot.get("score_calibration")
        if isinstance(profile, dict) and profile.get("buckets"):
            try:
                from core.redis_state import state
                from engine.score_calibration import PROFILE_STATE_KEY

                state.set_sync(PROFILE_STATE_KEY, json.dumps(profile, sort_keys=True, default=str))
            except Exception:
                logger.warning("[continuous_improvement] shadow score profile persistence failed", exc_info=True)
    reviewed = await review_snapshot(
        snapshot,
        request_external=request_external,
        request_gemini=request_gemini,
    )
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
        provider_reviews={
            "status": dict(reviewed.get("provider_status") or {}),
            "openai": reviewed.get("external_review"),
            "gemini": reviewed.get("gemini_review"),
        },
    )
    await _persist_latest_review(report)
    paths = write_review_artifacts(report, output_dir) if output_dir else None
    return report, paths
