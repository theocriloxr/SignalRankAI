from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any

from core.redis_state import state

from .weekly_review import run_weekly_review

logger = logging.getLogger(__name__)
_LAST_RUN_KEY = "signalrankai:continuous_improvement:last_weekly_run"


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
    report, paths = await run_weekly_review(days=7, request_external=external, output_dir=output_dir)
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
