from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

from utils.async_runner import run_sync

logger = logging.getLogger(__name__)


async def run_automated_audit(cycle_no: int, strict_candidates_count: int, final_signals_count: int) -> dict[str, Any]:
    """Run an automated Gemini audit for this cycle when the engine rejected good candidates.

    This is a lightweight wrapper that delegates to services.gemini_ml.run_gemini_review_pipeline
    which already collects DB aggregates. We keep this async so engine can call via run_sync.
    """
    try:
        api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
        if not api_key:
            return {"ok": False, "error": "GEMINI_API_KEY not configured"}

        enabled = str(os.getenv("AUTO_ANALYST_ENABLED", "1")).strip().lower() in {"1", "true", "yes"}
        if not enabled:
            return {"ok": False, "error": "automated analyst disabled"}

        interval = max(1, int(os.getenv("AUTO_ANALYST_INTERVAL", "10") or 10))
        if cycle_no % interval != 0:
            return {"ok": False, "skipped": True, "reason": "interval_mismatch"}

        # Call the robust pipeline that collects DB aggregates and runs the Gemini review.
        try:
            from services import gemini_ml
            res = await gemini_ml.run_gemini_review_pipeline(trigger=f"automated_cycle_{cycle_no}", scope="weekly")
            logger.info("[automated_analyst] Gemini audit completed for cycle %s", cycle_no)
            return dict(res or {})
        except Exception as exc:
            logger.exception("[automated_analyst] gemini audit failed: %s", exc)
            return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("[automated_analyst] failed: %s", exc)
        return {"ok": False, "error": str(exc)}
