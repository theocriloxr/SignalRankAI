#!/usr/bin/env python
"""
AI Feedback Loop Worker (Macro-Adjustments)

This worker runs periodically (daily/weekly) to review performance data
and use Gemini to recommend engine parameter adjustments.

This creates a "Chief Investment Officer" layer that:
- Monitors win rate, profit factor, and signal quality
- Uses Gemini to analyze trading performance
- Dynamically adjusts base thresholds via Redis

Run with: python -m worker.ai_feedback
Schedule: Daily at midnight or via cron
"""
from utils.timeutils import now_utc_naive

import os
import sys
import json
import logging
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PerformanceStats:
    """Trading performance statistics for review period."""
    win_rate: float = 0.0
    total_trades: int = 0
    profit_factor: float = 0.0
    current_base_threshold: float = 0.30
    average_ml_auc: float = 0.0
    avg_score: float = 0.0
    signals_issued: int = 0
    signals_rejected: int = 0


async def gather_performance_stats(days: int = 7) -> PerformanceStats:
    """Gather performance statistics from the database."""
    stats = PerformanceStats()
    
    try:
        from db.session import get_session
        from sqlalchemy import text
        
        since = now_utc_naive() - timedelta(days=days)
        
        async with get_session() as session:
            # Get outcome statistics
            row = await session.execute(
                text("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN status IN ('tp','tp1','tp2','tp3','partial_tp') THEN 1 ELSE 0 END) as wins,
                        AVG(r_multiple) as avg_r,
                        SUM(r_multiple) as net_r
                    FROM outcomes 
                    WHERE closed_at >= :since
                """),
                {"since": since}
            )
            result = row.first()
            
            if result:
                total = int(result[0] or 0)
                wins = int(result[1] or 0)
                stats.total_trades = total
                stats.win_rate = wins / max(1, total)
                stats.profit_factor = abs(float(result[3] or 0.0) / max(0.01, float(result[2] or 0.0) * (total - wins))) if total > 0 else 0.0
            
            # Get ML threshold from Redis or env
            try:
                from core.redis_state import state
                if state.has_redis_sync():
                    redis = state.get_redis_sync()
                    if redis:
                        threshold = redis.get("ENGINE_BASE_THRESHOLD")
                        if threshold:
                            stats.current_base_threshold = float(threshold)
            except Exception:
                pass
            
            stats.current_base_threshold = float(os.getenv("ML_PROB_THRESHOLD", "0.30"))
            
            # Get average ML AUC
            try:
                from core.redis_state import state
                if state.has_redis_sync():
                    redis = state.get_redis_sync()
                    if redis:
                        auc = redis.get("ml:model:auc")
                        if auc:
                            stats.average_ml_auc = float(auc)
            except Exception:
                pass
            
            # Get signal counts
            issued_row = await session.execute(
                text("""
                    SELECT COUNT(*) FROM signals 
                    WHERE created_at >= :since AND status = 'issued'
                """),
                {"since": since}
            )
            stats.signals_issued = int(issued_row.scalar() or 0)
            
            rejected_row = await session.execute(
                text("""
                    SELECT COUNT(*) FROM ml_rejected_signals 
                    WHERE created_at >= :since
                """),
                {"since": since}
            )
            stats.signals_rejected = int(rejected_row.scalar() or 0)
            
            # Get average score
            score_row = await session.execute(
                text("""
                    SELECT AVG(score) FROM signals 
                    WHERE created_at >= :since AND score IS NOT NULL
                """),
                {"since": since}
            )
            stats.avg_score = float(score_row.scalar() or 0.0)
                
    except Exception as e:
        logger.warning(f"[ai_feedback] Failed to gather stats: {e}")
    
    return stats


async def get_gemini_recommendation(stats: PerformanceStats) -> dict:
    """Return a governed AI threshold proposal; OpenAI first, Gemini/rules fallback."""
    stats_payload = {
        "win_rate": float(stats.win_rate),
        "total_trades": int(stats.total_trades),
        "profit_factor": float(stats.profit_factor),
        "current_base_threshold": float(stats.current_base_threshold),
        "average_ml_auc": float(stats.average_ml_auc),
        "avg_signal_score": float(stats.avg_score),
        "signals_issued": int(stats.signals_issued),
        "signals_rejected": int(stats.signals_rejected),
    }
    try:
        from services.openai_ai import openai_available, provider_order, threshold_recommendation
        order = provider_order()
        if openai_available() and "openai" in order and (
            "gemini" not in order or order.index("openai") < order.index("gemini")
        ):
            response = await threshold_recommendation(stats_payload)
            if response.get("ok"):
                data = dict(response.get("data") or {})
                return {
                    "new_threshold": max(0.15, min(0.60, float(data.get("new_threshold")))),
                    "reason": str(data.get("reason") or "OpenAI governed proposal")[:800],
                    "provider": "openai",
                    "model": response.get("model"),
                    "confidence": float(data.get("confidence") or 0.0),
                    "requires_forward_test": True,
                }
    except Exception as exc:
        logger.debug("[ai_feedback] OpenAI proposal unavailable: %s", type(exc).__name__)

    # Gemini compatibility fallback. Older deployments may not expose the
    # historical GeminiValidator class, so failure drops into deterministic rules.
    try:
        from services.gemini_ml import _call_gemini, gemini_available

        if gemini_available():
            prompt = f"""
You are an AI Trading Systems Architect. Review this aggregate performance data:
{json.dumps(stats_payload)}

Propose one ML probability threshold between 0.15 and 0.60.
Do not optimize win rate alone. Consider sample size, expectancy and model quality.
This is a proposal only and must be forward-tested before any owner-approved change.

Reply ONLY as JSON:
{{"new_threshold": 0.35, "reason": "brief evidence-based reason"}}
"""
            raw = await _call_gemini(prompt, max_tokens=220)
            if raw:
                try:
                    recom = json.loads(raw)
                except json.JSONDecodeError:
                    import re
                    match = re.search(r'\{[^{}]*\}', raw)
                    recom = json.loads(match.group()) if match else {}
                if isinstance(recom, dict) and recom.get("new_threshold") is not None:
                    return {
                        "new_threshold": max(0.15, min(0.60, float(recom["new_threshold"]))),
                        "reason": str(recom.get("reason") or "Gemini governed proposal")[:800],
                        "provider": "gemini",
                        "requires_forward_test": True,
                    }
    except Exception as exc:
        logger.debug("[ai_feedback] Gemini proposal unavailable: %s", type(exc).__name__)

    # Deterministic proposal fallback. Never auto-applied.
    new_threshold = stats.current_base_threshold
    reason = "rule_based"
    if stats.total_trades < 30:
        reason = "insufficient_resolved_sample_hold_threshold"
    elif stats.win_rate < 0.45:
        new_threshold = min(0.60, stats.current_base_threshold + 0.05)
        reason = "win_rate_low_tighten_candidate"
    elif stats.win_rate > 0.60 and stats.profit_factor > 1.5 and stats.average_ml_auc >= 0.70:
        new_threshold = max(0.15, stats.current_base_threshold - 0.02)
        reason = "strong_multi_metric_evidence_loosen_candidate"
    elif stats.average_ml_auc < 0.60:
        new_threshold = min(0.60, stats.current_base_threshold + 0.03)
        reason = "ml_auc_low_tighten_candidate"

    return {
        "new_threshold": new_threshold,
        "reason": reason,
        "provider": "local",
        "requires_forward_test": True,
    }

async def apply_recommendation(recommendation: dict) -> bool:
    """Record a proposal without changing runtime or production configuration.

    The historical function name is retained for import compatibility. AI
    recommendations are advisory and must pass experiment and owner approval
    gates before a normal, audited configuration deployment.
    """
    try:
        new_threshold = float(recommendation.get("new_threshold", 0.30))
        new_threshold = max(0.15, min(0.60, new_threshold))
        reason = str(recommendation.get("reason", "unknown"))
        proposal = {
            "kind": "parameter",
            "parameter": "ML_PROB_THRESHOLD",
            "proposed_value": new_threshold,
            "reason": reason,
            "status": "proposed",
            "requires_owner_approval": True,
            "auto_apply": False,
            "created_at": now_utc_naive().isoformat(),
        }
        try:
            from core.redis_state import state
            state.set_sync(
                "signalrankai:continuous_improvement:last_parameter_proposal",
                json.dumps(proposal),
                ex=2592000,
            )
        except Exception as e:
            logger.warning(f"[ai_feedback] proposal persistence unavailable: {e}")
        logger.info(
            "[ai_feedback] parameter proposal recorded value=%s auto_apply=0 owner_approval=required",
            new_threshold,
        )
        return True
        
    except Exception as e:
        logger.error(f"[ai_feedback] Failed to apply recommendation: {e}")
        return False


async def run_ai_feedback(force: bool = False) -> dict:
    """
    Main entry point for AI feedback loop.
    
    Args:
        force: Force run even if recently Run
    
    Returns:
        dict with results: success, stats, recommendation
    """
    import time
    
    # Check cooldown (run at most once per day)
    if not force:
        try:
            from core.redis_state import state
            if state.has_redis_sync():
                redis = state.get_redis_sync()
                if redis:
                    last_run = redis.get("AI_FEEDBACK_LAST_RUN")
                    if last_run:
                        last_run_time = float(last_run)
                        hours_since = (time.time() - last_run_time) / 3600
                        if hours_since < 24:
                            logger.debug(f"[ai_feedback] Skipping - ran {hours_since:.1f}h ago")
                            return {"skipped": True, "hours_since": hours_since}
        except Exception:
            pass
    
    logger.info("[ai_feedback] Running AI feedback loop...")
    
    # Gather stats
    stats = await gather_performance_stats(days=7)
    logger.info(f"[ai_feedback] Stats: win_rate={stats.win_rate:.1%}, trades={stats.total_trades}, ml_auc={stats.average_ml_auc:.3f}")
    
    # Get Gemini recommendation
    recommendation = await get_gemini_recommendation(stats)
    logger.info(f"[ai_feedback] AI recommendation proposal: {recommendation}")
    
    # Record recommendation only. This never mutates the active threshold.
    success = await apply_recommendation(recommendation)
    
    # Update last run timestamp
    try:
        from core.redis_state import state
        if state.has_redis_sync():
            redis = state.get_redis_sync()
            if redis:
                redis.set("AI_FEEDBACK_LAST_RUN", str(time.time()))
    except Exception:
        pass
    
    return {
        "success": success,
        "status": "proposal_recorded" if success else "proposal_failed",
        "auto_applied": False,
        "stats": {
            "win_rate": stats.win_rate,
            "total_trades": stats.total_trades,
            "profit_factor": stats.profit_factor,
            "ml_auc": stats.average_ml_auc,
            "avg_score": stats.avg_score,
        },
        "recommendation": recommendation,
    }


def main():
    """CLI entry point."""
    import asyncio
    
    result = asyncio.run(run_ai_feedback(force=True))
    
    if result.get("skipped"):
        print(f"Skipped - ran {result.get('hours_since', 0):.1f}h ago")
    elif result.get("success"):
        print("AI feedback loop completed successfully")
        print(f"Stats: {result.get('stats')}")
        print(f"Recommendation: {result.get('recommendation')}")
    else:
        print("AI feedback loop failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
