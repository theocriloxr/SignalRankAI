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
        
        since = datetime.utcnow() - timedelta(days=days)
        
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
    """Ask Gemini for parameter adjustment recommendation."""
    try:
        # Try to use GeminiValidator if available
        from services.gemini_ml import GeminiValidator
        
        validator = GeminiValidator()
        
        prompt = f"""
You are an AI Trading Systems Architect. Review the following {7}-day performance data for our trading engine:

{json.dumps({
    "win_rate": f"{stats.win_rate:.1%}",
    "total_trades": stats.total_trades,
    "profit_factor": f"{stats.profit_factor:.2f}",
    "current_base_threshold": stats.current_base_threshold,
    "average_ml_auc": f"{stats.average_ml_auc:.3f}",
    "avg_signal_score": f"{stats.avg_score:.1f}",
    "signals_issued": stats.signals_issued,
    "signals_rejected": stats.signals_rejected,
})}

Our targets:
- Win rate: > 55%
- Profit factor: > 1.5
- ML AUC: > 0.80

Based on the current metrics, should we increase or decrease the 'base_threshold' to improve signal quality? 

Respond ONLY with a JSON object containing:
- "new_threshold": float (recommended base threshold, e.g., 0.35)
- "reason": string (short explanation)

Example: {{"new_threshold": 0.35, "reason": "Low win rate suggests we are taking too many low-quality trades. Increasing threshold to filter noise."}}
"""
        
        response = await validator.generate_content(prompt)
        
        # Parse JSON response
        try:
            # Try direct JSON parse first
            recom = json.loads(response)
        except json.JSONDecodeError:
            # Extract JSON from text response
            import re
            match = re.search(r'\{[^{}]*\}', response)
            if match:
                recom = json.loads(match.group())
            else:
                recom = {"new_threshold": stats.current_base_threshold, "reason": "Failed to parse Gemini response"}
        
        return recom
        
    except ImportError:
        # Fallback: simple rule-based adjustment
        logger.info("[ai_feedback] Gemini not available, using rule-based adjustment")
        
        new_threshold = stats.current_base_threshold
        reason = "rule_based"
        
        if stats.win_rate < 0.45:
            # Poor win rate - tighten threshold
            new_threshold = min(0.60, stats.current_base_threshold + 0.05)
            reason = "win_rate_low"
        elif stats.win_rate > 0.60:
            # Excellent win rate - loosen threshold
            new_threshold = max(0.15, stats.current_base_threshold - 0.02)
            reason = "win_rate_high"
        elif stats.average_ml_auc < 0.60:
            # Poor ML model - tighten threshold
            new_threshold = min(0.60, stats.current_base_threshold + 0.03)
            reason = "ml_auc_low"
        elif stats.average_ml_auc > 0.80:
            # Excellent ML model - loosen threshold
            new_threshold = max(0.15, stats.current_base_threshold - 0.02)
            reason = "ml_auc_high"
        
        return {"new_threshold": new_threshold, "reason": reason}
        
    except Exception as e:
        logger.warning(f"[ai_feedback] Gemini recommendation failed: {e}")
        return {"new_threshold": stats.current_base_threshold, "reason": f"error: {e}"}


async def apply_recommendation(recommendation: dict) -> bool:
    """Apply the AI's recommended threshold via Redis."""
    try:
        new_threshold = float(recommendation.get("new_threshold", 0.30))
        
        # Clamp to safe bounds
        new_threshold = max(0.15, min(0.60, new_threshold))
        
        reason = str(recommendation.get("reason", "unknown"))
        
        # Store in Redis
        try:
            from core.redis_state import state
            if state.has_redis_sync():
                redis = state.get_redis_sync()
                if redis:
                    redis.set("ENGINE_BASE_THRESHOLD", str(new_threshold))
                    logger.info(f"[AI Ops] Gemini adjusted threshold to {new_threshold}. Reason: {reason}")
                    return True
        except Exception as e:
            logger.warning(f"[ai_feedback] Redis update failed: {e}")
        
        # Fallback: update environment variable
        os.environ["ML_PROB_THRESHOLD"] = str(new_threshold)
        logger.info(f"[AI Ops] Adjusted ML_PROB_THRESHOLD env to {new_threshold}. Reason: {reason}")
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
    logger.info(f"[ai_feedback] Recommendation: {recommendation}")
    
    # Apply recommendation
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
