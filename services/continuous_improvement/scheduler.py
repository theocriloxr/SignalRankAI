from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any

from core.redis_state import state

from .github_dispatch import dispatch_refactor_workflow
from .weekly_review import run_weekly_review

logger = logging.getLogger(__name__)
_LAST_RUN_KEY = "signalrankai:continuous_improvement:last_weekly_run"


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


async def _notify_admins(report) -> dict[str, Any]:
    """Send one bounded review-only summary through the canonical Telegram helper."""
    if not _truthy("CONTINUOUS_IMPROVEMENT_ADMIN_NOTIFY_ENABLED", True):
        return {"enabled": False, "sent": 0, "attempted": 0}
    try:
        from config import OWNER_IDS, ADMIN_IDS
        from services.waitlist_jobs import _send_telegram_dm
        recipients = sorted({int(x) for x in ((OWNER_IDS or set()) | (ADMIN_IDS or set()))})
    except Exception:
        recipients = []
    if not recipients:
        return {"enabled": True, "sent": 0, "attempted": 0, "reason": "admin_recipients_missing"}

    recommendations = list(getattr(report, "recommendations", ()) or ())
    incidents = list(getattr(report, "incidents", ()) or ())
    lines = [
        "🧠 SignalRank weekly improvement review",
        "",
        f"Review: {getattr(report, 'review_id', 'unknown')}",
        f"Recommendations: {len(recommendations)}",
        f"Incidents: {len(incidents)}",
        f"External review: {getattr(report, 'external_review_status', 'not_requested')}",
        "",
    ]
    for idx, recommendation in enumerate(recommendations[:5], start=1):
        title = str(getattr(recommendation, "title", "Improvement"))[:180]
        rationale = str(getattr(recommendation, "rationale", ""))[:300]
        provider = str(getattr(recommendation, "provider", "local"))[:32]
        risk = str(getattr(recommendation, "risk", "medium"))[:24]
        tests = list(getattr(recommendation, "acceptance_tests", ()) or ())
        lines.extend([
            f"{idx}. {title}",
            f"Provider: {provider} | Risk: {risk}",
            f"Why: {rationale}",
        ])
        if tests:
            lines.append(f"Test: {str(tests[0])[:240]}")
        lines.append("")
    lines.extend([
        "No change was auto-applied.",
        "Use /ai_audit or /codex_audit for detailed evidence before approving an experiment.",
    ])
    message = "\n".join(lines)[:3900]

    sent = 0
    for recipient in recipients:
        try:
            await _send_telegram_dm(int(recipient), message)
            sent += 1
        except Exception:
            logger.warning(
                "[continuous_improvement] admin notification failed chat=%s",
                recipient,
                exc_info=True,
            )
    return {"enabled": True, "sent": sent, "attempted": len(recipients)}


def review_is_due(*, now: float | None = None, interval_seconds: int = 604800) -> bool:
    current = float(time.time() if now is None else now)
    try:
        last = float(state.get_sync(_LAST_RUN_KEY) or 0.0)
    except Exception:
        last = 0.0
    return current - last >= max(3600, int(interval_seconds))


async def run_scheduled_review_once(*, now: float | None = None) -> dict[str, Any]:
    interval = max(3600, int(os.getenv("CONTINUOUS_IMPROVEMENT_REVIEW_INTERVAL_SECONDS", "604800") or 604800))
    current = float(time.time() if now is None else now)
    if not review_is_due(now=current, interval_seconds=interval):
        return {"ok": True, "skipped": True, "reason": "not_due"}
    output_dir = Path(os.getenv("CONTINUOUS_IMPROVEMENT_ARTIFACT_DIR", "artifacts/continuous-improvement"))
    external = str(os.getenv("CONTINUOUS_IMPROVEMENT_OPENAI_ENABLED", "0")).lower() in {"1", "true", "yes", "on"}
    gemini = str(os.getenv("CONTINUOUS_IMPROVEMENT_GEMINI_ENABLED", "0")).lower() in {"1", "true", "yes", "on"}
    report, paths = await run_weekly_review(
        days=7,
        request_external=external,
        request_gemini=gemini,
        output_dir=output_dir,
    )
    refactor_dispatch = await dispatch_refactor_workflow(report)
    admin_notification = await _notify_admins(report)
    try:
        state.set_sync(_LAST_RUN_KEY, str(current), ex=max(interval * 3, 2592000))
    except Exception:
        logger.warning("[continuous_improvement] could not persist schedule cursor", exc_info=True)
    return {
        "ok": True,
        "skipped": False,
        "review_id": report.review_id,
        "recommendations": len(report.recommendations),
        "incidents": len(report.incidents),
        "artifacts": [str(path) for path in paths or ()],
        "production_mutation": False,
        "refactor_dispatch": refactor_dispatch,
        "admin_notification": admin_notification,
    }


async def continuous_improvement_loop(stop_event: asyncio.Event) -> None:
    poll_seconds = max(300, int(os.getenv("CONTINUOUS_IMPROVEMENT_POLL_SECONDS", "3600") or 3600))
    initial_delay = max(0, int(os.getenv("CONTINUOUS_IMPROVEMENT_STARTUP_DELAY_SECONDS", "300") or 300))
    if initial_delay:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=initial_delay)
            return
        except asyncio.TimeoutError:
            pass
    while not stop_event.is_set():
        try:
            result = await run_scheduled_review_once()
            logger.info("[continuous_improvement] scheduled review result=%s", result)
        except Exception:
            logger.exception("[continuous_improvement] scheduled review failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except asyncio.TimeoutError:
            continue
