from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy import text

from db.session import get_session, is_db_configured
from services.codex_governance import run_codex_governance_review
from services.gemini_ml import run_gemini_review_pipeline

logger = logging.getLogger(__name__)


async def _fetch_completed_trades(limit: int = 200) -> List[Dict[str, Any]]:
    if not is_db_configured():
        return []
    async with get_session() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT s.signal_id, s.asset, s.timeframe, s.direction, s.entry, s.stop_loss, s.take_profit,
                           s.score, o.status AS outcome_status, o.closed_at
                    FROM signals s
                    JOIN outcomes o ON o.signal_id = s.signal_id
                    WHERE o.status IN ('tp','tp1','tp2','tp3','partial_tp','sl')
                      AND o.closed_at >= :since
                    ORDER BY o.closed_at DESC
                    LIMIT :lim
                    """
                ),
                {"since": datetime.utcnow() - timedelta(days=14), "lim": int(limit)},
            )
        ).mappings().all()
        await session.commit()
    return [dict(r) for r in rows]


async def _fetch_recent_logs(limit: int = 200) -> List[Dict[str, Any]]:
    if not is_db_configured():
        return []
    async with get_session() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id, decision, reason, meta, created_at
                    FROM decision_log
                    WHERE decision IN ('error','rejected','skipped')
                    ORDER BY created_at DESC
                    LIMIT :lim
                    """
                ),
                {"lim": int(limit)},
            )
        ).mappings().all()
        await session.commit()
    return [dict(r) for r in rows]


async def run_ai_review_audit() -> Dict[str, Any]:
    trades = await _fetch_completed_trades()
    logs = await _fetch_recent_logs()
    base = await run_gemini_review_pipeline(trigger="ai_reviewer", scope="weekly")
    codex = await run_codex_governance_review(trigger="ai_reviewer", scope="weekly")
    result = {
        "ran_at": datetime.utcnow().isoformat(),
        "trades_sampled": len(trades),
        "log_events_sampled": len(logs),
        "gemini_ok": bool(base.get("ok")),
        "gemini_summary": {
            "received": base.get("received"),
            "feature_suggestions": base.get("feature_suggestions"),
        },
        "codex_governance_ok": bool(codex.get("ok")),
        "codex_governance_summary": {
            "assessment": (codex.get("review") or {}).get("assessment"),
            "highest_risk_findings": (codex.get("review") or {}).get("highest_risk_findings"),
            "guardrail": codex.get("guardrail"),
        },
    }
    if is_db_configured():
        async with get_session() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO runtime_state(key, value, expires_at, updated_at)
                    VALUES (:k, :v::jsonb, NULL, NOW())
                    ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
                    """
                ),
                {"k": "ai_reviewer_last_run", "v": json.dumps(result)},
            )
            await session.commit()
    return result


async def main() -> None:
    out = await run_ai_review_audit()
    logger.info("[ai_reviewer] completed: %s", out)


if __name__ == "__main__":
    asyncio.run(main())
