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
    """Trading performance statistics for one evidence window."""
    win_rate: float = 0.0
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    gross_win_r: float = 0.0
    gross_loss_r: float = 0.0
    expectancy_r: float = 0.0
    net_r: float = 0.0
    profit_factor: float = 0.0
    current_base_threshold: float = 0.50
    threshold_source: str = "fallback"
    average_ml_auc: float = 0.0
    avg_score: float = 0.0
    signals_issued: int = 0
    signals_rejected: int = 0


async def gather_performance_stats(days: int = 7) -> PerformanceStats:
    """Gather proof-backed performance and the active model threshold."""
    stats = PerformanceStats()

    try:
        from db.session import get_session
        from sqlalchemy import text

        since = now_utc_naive() - timedelta(days=days)

        async with get_session() as session:
            # Profit factor is gross positive R divided by absolute gross
            # negative R. The previous implementation derived it from net R,
            # average R and the loss count, which is not profit factor and could
            # materially mislead the AI parameter reviewer.
            row = await session.execute(
                text("""
                    SELECT
                        COUNT(*) FILTER (WHERE r_multiple IS NOT NULL) AS total,
                        COUNT(*) FILTER (WHERE r_multiple > 0) AS wins,
                        COUNT(*) FILTER (WHERE r_multiple < 0) AS losses,
                        COUNT(*) FILTER (WHERE r_multiple = 0) AS breakeven,
                        COALESCE(SUM(CASE WHEN r_multiple > 0 THEN r_multiple ELSE 0 END), 0) AS gross_win_r,
                        ABS(COALESCE(SUM(CASE WHEN r_multiple < 0 THEN r_multiple ELSE 0 END), 0)) AS gross_loss_r,
                        COALESCE(AVG(r_multiple) FILTER (WHERE r_multiple IS NOT NULL), 0) AS expectancy_r,
                        COALESCE(SUM(r_multiple), 0) AS net_r
                    FROM outcomes
                    WHERE closed_at >= :since
                      AND r_multiple IS NOT NULL
                """),
                {"since": since},
            )
            result = row.first()

            if result:
                stats.total_trades = int(result[0] or 0)
                stats.wins = int(result[1] or 0)
                stats.losses = int(result[2] or 0)
                stats.breakeven = int(result[3] or 0)
                stats.gross_win_r = float(result[4] or 0.0)
                stats.gross_loss_r = float(result[5] or 0.0)
                stats.expectancy_r = float(result[6] or 0.0)
                stats.net_r = float(result[7] or 0.0)
                decisive = stats.wins + stats.losses
                stats.win_rate = stats.wins / decisive if decisive > 0 else 0.0
                if stats.gross_loss_r > 0:
                    stats.profit_factor = stats.gross_win_r / stats.gross_loss_r
                elif stats.gross_win_r > 0:
                    # Keep JSON finite while representing a no-loss sample.
                    stats.profit_factor = 10.0
                else:
                    stats.profit_factor = 0.0

            # The promoted model's calibration-window classification threshold
            # is the production decision cutoff. Prefer it over historical env
            # and Redis base-threshold values when available.
            threshold_found = False
            try:
                from ml.inference import MLFilter

                ml_filter = MLFilter()
                certified = (
                    ml_filter.recommended_raw_threshold()
                    if bool(getattr(ml_filter, "active", False))
                    else None
                )
                if certified is not None:
                    stats.current_base_threshold = float(certified)
                    stats.threshold_source = "promoted_model"
                    threshold_found = True
                    metrics = dict(getattr(ml_filter, "metrics", {}) or {})
                    for auc_key in ("auc", "roc_auc", "test_auc"):
                        if metrics.get(auc_key) is not None:
                            stats.average_ml_auc = float(metrics[auc_key])
                            break
            except Exception as exc:
                logger.debug("[ai_feedback] promoted model metadata unavailable: %s", type(exc).__name__)

            if not threshold_found:
                try:
                    from core.redis_state import state

                    if state.has_redis_sync():
                        redis = state.get_redis_sync()
                        if redis:
                            threshold = redis.get("ENGINE_BASE_THRESHOLD")
                            if threshold is not None:
                                stats.current_base_threshold = float(threshold)
                                stats.threshold_source = "redis_base"
                                threshold_found = True
                            if stats.average_ml_auc <= 0:
                                auc = redis.get("ml:model:auc")
                                if auc is not None:
                                    stats.average_ml_auc = float(auc)
                except Exception:
                    pass

            if not threshold_found:
                stats.current_base_threshold = float(os.getenv("ML_PROB_THRESHOLD", "0.50") or 0.50)
                stats.threshold_source = "env_fallback"

            issued_row = await session.execute(
                text("""
                    SELECT COUNT(*) FROM signals
                    WHERE created_at >= :since AND status = 'issued'
                """),
                {"since": since},
            )
            stats.signals_issued = int(issued_row.scalar() or 0)

            rejected_row = await session.execute(
                text("""
                    SELECT COUNT(*) FROM ml_rejected_signals
                    WHERE created_at >= :since
                """),
                {"since": since},
            )
            stats.signals_rejected = int(rejected_row.scalar() or 0)

            score_row = await session.execute(
                text("""
                    SELECT AVG(score) FROM signals
                    WHERE created_at >= :since AND score IS NOT NULL
                """),
                {"since": since},
            )
            stats.avg_score = float(score_row.scalar() or 0.0)

    except Exception as e:
        logger.warning("[ai_feedback] Failed to gather stats: %s", e)

    return stats


def _proposal_bounds(current_threshold: float) -> tuple[float, float]:
    """Keep advisory threshold experiments near the promoted cutoff."""
    try:
        current = float(current_threshold)
    except Exception:
        current = 0.50
    current = max(0.05, min(0.95, current))
    try:
        max_delta = float(os.getenv("AI_THRESHOLD_PROPOSAL_MAX_DELTA", "0.05") or 0.05)
    except Exception:
        max_delta = 0.05
    max_delta = max(0.01, min(0.15, max_delta))
    return max(0.05, current - max_delta), min(0.95, current + max_delta)


async def get_gemini_recommendation(stats: PerformanceStats) -> dict:
    """Return a governed threshold experiment proposal; OpenAI first."""
    lower, upper = _proposal_bounds(stats.current_base_threshold)
    stats_payload = {
        "win_rate": float(stats.win_rate),
        "total_trades": int(stats.total_trades),
        "wins": int(stats.wins),
        "losses": int(stats.losses),
        "breakeven": int(stats.breakeven),
        "gross_win_r": float(stats.gross_win_r),
        "gross_loss_r": float(stats.gross_loss_r),
        "expectancy_r": float(stats.expectancy_r),
        "net_r": float(stats.net_r),
        "profit_factor": float(stats.profit_factor),
        "current_base_threshold": float(stats.current_base_threshold),
        "threshold_source": str(stats.threshold_source),
        "proposal_min": float(lower),
        "proposal_max": float(upper),
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
                proposed = max(lower, min(upper, float(data.get("new_threshold"))))
                return {
                    "new_threshold": proposed,
                    "current_threshold": float(stats.current_base_threshold),
                    "allowed_min": lower,
                    "allowed_max": upper,
                    "threshold_source": stats.threshold_source,
                    "reason": str(data.get("reason") or "OpenAI governed proposal")[:800],
                    "provider": "openai",
                    "model": response.get("model"),
                    "confidence": float(data.get("confidence") or 0.0),
                    "requires_forward_test": True,
                }
    except Exception as exc:
        logger.debug("[ai_feedback] OpenAI proposal unavailable: %s", type(exc).__name__)

    try:
        from services.gemini_ml import _call_gemini, gemini_available

        if gemini_available():
            prompt = f"""
You are an AI Trading Systems Architect. Review this aggregate performance data:
{json.dumps(stats_payload)}

The active promoted-model raw threshold is {stats.current_base_threshold:.4f}.
Propose one raw-probability threshold between {lower:.4f} and {upper:.4f}.
Do not optimize win rate alone. Use decisive sample size, expectancy R, gross-R profit factor,
model AUC, calibration context, issued/rejected balance and downside risk. If evidence is
insufficient, hold the current threshold. This is a proposal only and must be forward-tested
before any owner-approved change.

Reply ONLY as JSON:
{{"new_threshold": {stats.current_base_threshold:.4f}, "reason": "brief evidence-based reason"}}
"""
            raw = await _call_gemini(prompt, max_tokens=260)
            if raw:
                try:
                    recom = json.loads(raw)
                except json.JSONDecodeError:
                    import re
                    match = re.search(r'\{[^{}]*\}', raw)
                    recom = json.loads(match.group()) if match else {}
                if isinstance(recom, dict) and recom.get("new_threshold") is not None:
                    proposed = max(lower, min(upper, float(recom["new_threshold"])))
                    return {
                        "new_threshold": proposed,
                        "current_threshold": float(stats.current_base_threshold),
                        "allowed_min": lower,
                        "allowed_max": upper,
                        "threshold_source": stats.threshold_source,
                        "reason": str(recom.get("reason") or "Gemini governed proposal")[:800],
                        "provider": "gemini",
                        "requires_forward_test": True,
                    }
    except Exception as exc:
        logger.debug("[ai_feedback] Gemini proposal unavailable: %s", type(exc).__name__)

    new_threshold = float(stats.current_base_threshold)
    reason = "rule_based_hold"
    decisive = int(stats.wins + stats.losses)
    if decisive < 30:
        reason = "insufficient_decisive_sample_hold_threshold"
    elif stats.expectancy_r < 0 or stats.profit_factor < 1.0:
        new_threshold = min(upper, stats.current_base_threshold + 0.03)
        reason = "negative_expectancy_tighten_candidate"
    elif (
        stats.win_rate > 0.60
        and stats.profit_factor > 1.5
        and stats.expectancy_r > 0
        and stats.average_ml_auc >= 0.70
    ):
        new_threshold = max(lower, stats.current_base_threshold - 0.02)
        reason = "positive_multi_metric_evidence_loosen_candidate"
    elif stats.average_ml_auc < 0.60:
        new_threshold = min(upper, stats.current_base_threshold + 0.03)
        reason = "ml_auc_low_tighten_candidate"

    return {
        "new_threshold": max(lower, min(upper, new_threshold)),
        "current_threshold": float(stats.current_base_threshold),
        "allowed_min": lower,
        "allowed_max": upper,
        "threshold_source": stats.threshold_source,
        "reason": reason,
        "provider": "local",
        "requires_forward_test": True,
    }


async def apply_recommendation(recommendation: dict) -> bool:
    """Persist an experiment proposal without mutating runtime configuration."""
    try:
        current = float(recommendation.get("current_threshold", 0.50) or 0.50)
        lower, upper = _proposal_bounds(current)
        if recommendation.get("allowed_min") is not None:
            lower = max(lower, float(recommendation["allowed_min"]))
        if recommendation.get("allowed_max") is not None:
            upper = min(upper, float(recommendation["allowed_max"]))
        new_threshold = max(lower, min(upper, float(recommendation.get("new_threshold", current))))
        reason = str(recommendation.get("reason", "unknown"))
        proposal = {
            "kind": "parameter",
            "parameter": "ML_PROB_THRESHOLD",
            "parameter_space": "raw_model_probability",
            "current_runtime_threshold": current,
            "threshold_source": str(recommendation.get("threshold_source") or "unknown"),
            "allowed_min": lower,
            "allowed_max": upper,
            "proposed_value": new_threshold,
            "reason": reason,
            "status": "proposed",
            "requires_forward_test": True,
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
            logger.warning("[ai_feedback] proposal persistence unavailable: %s", e)
        logger.info(
            "[ai_feedback] parameter proposal recorded current=%s proposed=%s range=[%s,%s] auto_apply=0",
            current,
            new_threshold,
            lower,
            upper,
        )
        return True
    except Exception as e:
        logger.error("[ai_feedback] Failed to record recommendation: %s", e)
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
