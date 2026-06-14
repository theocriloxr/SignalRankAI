"""
AI Feedback Loop Worker for SignalRankAI

Gemini-powered Chief Investment Officer that reviews weekly performance
and adjusts the engine's aggressiveness dynamically.

This creates a completely self-healing system that learns from outcomes.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


async def gather_performance_stats(days: int = 7) -> Dict[str, Any]:
    """
    Gather last N days of performance data from the database.
    
    Returns dict with win_rate, total_trades, profit_factor, etc.
    """
    stats = {
        "win_rate": 0.0,
        "total_trades": 0,
        "profit_factor": 0.0,
        "current_base_threshold": _env_float("ML_PROB_THRESHOLD", 0.30),
        "average_ml_auc": 0.70,
    }
    
    try:
        from db.session import get_session
        from sqlalchemy import text
        from datetime import datetime, timedelta
        
        since = datetime.utcnow() - timedelta(days=days)
        
        async with get_session() as session:
            # Get outcome statistics
            row = await session.execute(
                text("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN status IN ('tp','tp1','tp2','tp3','partial_tp') THEN 1 ELSE 0 END) as wins,
                        COALESCE(SUM(r_multiple), 0) as net_r
                    FROM outcomes 
                    WHERE closed_at >= :since
                """),
                {"since": since}
            )
            result = row.first()
            
            if result:
                total = int(result[0] or 0)
                wins = int(result[1] or 0)
                net_r = float(result[2] or 0.0)
                
                stats["total_trades"] = total
                stats["win_rate"] = wins / max(1, total) if total > 0 else 0.0
                stats["profit_factor"] = net_r / max(1, total) if total > 0 else 0.0
            
            # Get current AUC from Redis
            try:
                import redis as redis_client
                redis_url = os.getenv("REDIS_URL")
                if redis_url:
                    r = redis_client.from_url(redis_url, decode_responses=True)
                    auc_str = r.get("ml:model:auc")
                    r.close()
                    if auc_str:
                        stats["average_ml_auc"] = float(auc_str)
            except Exception as e:
                logger.debug(f"[ai_feedback] Failed to fetch AUC: {e}")
            
            # Get current threshold from Redis or env
            try:
                import redis as redis_client
                redis_url = os.getenv("REDIS_URL")
                if redis_url:
                    r = redis_client.from_url(redis_url, decode_responses=True)
                    thresh_str = r.get("ENGINE_BASE_THRESHOLD")
                    r.close()
                    if thresh_str:
                        stats["current_base_threshold"] = float(thresh_str)
            except Exception as e:
                logger.debug(f"[ai_feedback] Failed to fetch threshold: {e}")
    
    except Exception as e:
        logger.warning(f"[ai_feedback] Failed to gather performance stats: {e}")
    
    logger.info(f"[ai_feedback] Performance stats: {stats}")
    return stats


async def auto_adjust_engine_parameters() -> bool:
    """
    Main entry point: Gather performance data, ask Gemini for recommendations,
    and apply the AI's settings dynamically via Redis.
    
    Returns True if adjustment was made, False otherwise.
    """
    # Check if Gemini is enabled
    if not _env_bool("GEMINI_AI_FEEDBACK_ENABLED", True):
        logger.debug("[ai_feedback] Gemini AI feedback disabled")
        return False
    
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.warning("[ai_feedback] GEMINI_API_KEY not set")
        return False
    
    # Gather stats
    stats = await gather_performance_stats(days=7)
    
    # Check minimum sample size
    min_trades = int(os.getenv("AI_FEEDBACK_MIN_TRADES", "10"))
    if stats["total_trades"] < min_trades:
        logger.info(
            f"[ai_feedback] Only {stats['total_trades']} trades in last 7 days "
            f"(minimum {min_trades}). Skipping Gemini review."
        )
        return False
    
    # Build prompt for Gemini
    prompt = f"""
You are an AI Trading Systems Architect. Review the following 7-day performance data for our trading engine:

{json.dumps(stats, indent=2)}

Our goals are:
- Win rate > 55%
- Profit factor > 1.5

Based on the current metrics, should we increase or decrease the 'base_threshold' to improve signal quality?
Respond ONLY with a JSON object containing the new recommended threshold and a short reasoning.
Example: {{"new_threshold": 0.35, "reason": "Low win rate suggests we are taking too many low-quality trades. Increasing threshold to filter noise."}}
"""
    
    try:
        # Call Gemini
        import urllib.request
        import json
        
        model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        
        body = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 200},
        }).encode("utf-8")
        
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        
        # Parse JSON response
        try:
            response_data = json.loads(raw)
            text_content = response_data["candidates"][0]["content"]["parts"][0]["text"]
            
            # Extract JSON from response
            # Handle cases where Gemini wraps JSON in markdown code blocks
            if "```json" in text_content:
                text_content = text_content.split("```json")[1].split("```")[0]
            elif "```" in text_content:
                text_content = text_content.split("```")[1].split("```")[0]
            
            ai_recommendation = json.loads(text_content.strip())
            
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning(f"[ai_feedback] Failed to parse Gemini response: {e}")
            return False
        
        new_threshold = float(ai_recommendation.get("new_threshold", 0.30))
        reason = str(ai_recommendation.get("reason", ""))
        
        # Validate threshold range
        if new_threshold < 0.15 or new_threshold > 0.60:
            logger.warning(
                f"[ai_feedback] Gemini returned invalid threshold {new_threshold}. "
                f"Must be between 0.15 and 0.60"
            )
            new_threshold = max(0.15, min(0.60, new_threshold))
        
        # Apply to Redis
        try:
            import redis as redis_client
            redis_url = os.getenv("REDIS_URL")
            if redis_url:
                r = redis_client.from_url(redis_url, decode_responses=True)
                r.set("ENGINE_BASE_THRESHOLD", new_threshold)
                r.set("ENGINE_BASE_THRESHOLD_UPDATED_AT", datetime.utcnow().isoformat())
                r.set("ENGINE_BASE_THRESHOLD_REASON", reason)
                r.close()
                
                logger.info(
                    f"[ai_feedback] Gemini adjusted threshold to {new_threshold:.3f}. "
                    f"Reason: {reason}"
                )
                return True
        except Exception as e:
            logger.warning(f"[ai_feedback] Failed to apply threshold to Redis: {e}")
            return False
    
    except Exception as e:
        logger.warning(f"[ai_feedback] Gemini call failed: {e}")
        return False


async def run_ai_feedback_cycle() -> bool:
    """
    Run one cycle of AI feedback.
    Call this from your worker scheduler.
    """
    logger.info("[ai_feedback] Starting AI feedback cycle...")
    
    success = await auto_adjust_engine_parameters()
    
    if success:
        logger.info("[ai_feedback] AI feedback cycle complete - threshold adjusted")
    else:
        logger.info("[ai_feedback] AI feedback cycle complete - no adjustment made")
    
    return success


# Standalone test
if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    
    async def test():
        stats = await gather_performance_stats(days=7)
        print(f"\n=== Performance Stats ===")
        print(json.dumps(stats, indent=2))
        
        # Test adjustment (won't work without valid API key)
        result = await auto_adjust_engine_parameters()
        print(f"\n=== Adjustment Made: {result} ===")
    
    asyncio.run(test())
