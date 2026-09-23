from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict

from sqlalchemy import text

from db.session import get_session, is_db_configured
from services.codex_governance import (
    build_local_codex_recommendations,
    collect_codex_governance_context,
    run_external_gemini_aggregate_review,
)
from utils.timeutils import now_utc_naive

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


async def _openai_aggregate_review(context: Dict[str, Any]) -> dict[str, Any] | None:
    """Primary deep reviewer over aggregate-only evidence."""
    try:
        from services.openai_ai import openai_available, performance_review

        if not openai_available():
            return None
        result = await performance_review(context)
        return result
    except Exception as exc:
        logger.warning("[ai_reviewer] OpenAI aggregate review failed: %s", type(exc).__name__)
        return {"ok": False, "provider": "openai", "error": type(exc).__name__}


async def run_ai_review_audit() -> Dict[str, Any]:
    """Run a governed aggregate AI audit without mutating production behavior."""
    context = await collect_codex_governance_context(days=14)
    if not context.get("ok"):
        return {
            "ok": False,
            "ran_at": now_utc_naive().isoformat(),
            "error": str(context.get("error") or "governance_context_unavailable"),
            "production_mutation": False,
        }

    local = build_local_codex_recommendations(context)
    openai_task = asyncio.create_task(_openai_aggregate_review(context), name="ai-review-openai")
    gemini_task = None
    if _env_bool("AI_REVIEWER_GEMINI_SECONDARY_ENABLED", True):
        gemini_task = asyncio.create_task(
            run_external_gemini_aggregate_review(context, requested=True),
            name="ai-review-gemini",
        )

    openai_review = await openai_task
    gemini_review = await gemini_task if gemini_task is not None else None

    provider_performance = list(context.get("ai_provider_performance") or [])
    result = {
        "ok": True,
        "ran_at": now_utc_naive().isoformat(),
        "days": int(context.get("days") or 14),
        "summary": dict(context.get("summary") or {}),
        "ai_provider_performance": provider_performance[:20],
        "local_review": local,
        "openai_review": openai_review,
        "gemini_secondary_review": gemini_review,
        "provider_status": {
            "openai": (
                "completed" if openai_review and openai_review.get("ok")
                else "failed" if openai_review
                else "not_configured"
            ),
            "gemini": (
                "completed" if gemini_review and gemini_review.get("ok")
                else "failed" if gemini_review
                else "not_requested"
            ),
        },
        "guardrail": "recommendations_only_no_unattended_parameter_code_or_execution_changes",
        "external_data_scope": "aggregate_only_no_user_or_signal_ids",
        "production_mutation": False,
        "requires_owner_approval": True,
        "requires_forward_test": True,
    }
    if is_db_configured():
        async with get_session() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO runtime_state(key, value, expires_at, updated_at)
                    VALUES (:k, CAST(:v AS JSONB), NULL, NOW())
                    ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
                    """
                ),
                {"k": "ai_reviewer_last_run", "v": json.dumps(result, default=str)},
            )
            await session.commit()
    return result


async def main() -> None:
    out = await run_ai_review_audit()
    logger.info("[ai_reviewer] completed: %s", out)


if __name__ == "__main__":
    asyncio.run(main())
