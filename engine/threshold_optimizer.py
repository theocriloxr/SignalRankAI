"""
Adaptive Threshold Optimizer for SignalRankAI

Automatically adjusts ML confidence thresholds based on:
- Historical win rate
- ROI/Risk-Reward ratio  
- Signal volume requirements
- Gemini AI suggestions

This module provides dynamic thresholds that evolve with performance
to maximize signal accuracy, win rate, ROI and risk-reward ratio.
"""

import os
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# Default threshold bounds (safety limits)
DEFAULT_ML_THRESHOLD_MIN = float(os.getenv("ML_THRESHOLD_MIN", "0.30"))
DEFAULT_ML_THRESHOLD_MAX = float(os.getenv("ML_THRESHOLD_MAX", "0.85"))
DEFAULT_ML_THRESHOLD_DEFAULT = float(os.getenv("ML_THRESHOLD_DEFAULT", "0.55"))

# Performance targets
TARGET_WIN_RATE = float(os.getenv("TARGET_WIN_RATE", "0.60"))  # 60% win rate target
TARGET_AVG_R = float(os.getenv("TARGET_AVG_R", "1.5"))  # 1.5R average profit
MIN_SIGNALS_PER_CYCLE = int(os.getenv("MIN_SIGNALS_PER_CYCLE", "3"))

# Dynamic gate bounds (safety rails to avoid over-tight/over-loose behavior)
# Keep the floor lower so the optimizer cannot starve the bot during weak regimes.
MIN_SCORE_FLOOR = float(os.getenv("MIN_SCORE_FLOOR", "40.0"))
MIN_SCORE_CEILING = float(os.getenv("MIN_SCORE_CEILING", "75.0"))
CONFLUENCE_MIN_FLOOR = float(os.getenv("CONFLUENCE_MIN_FLOOR", "0.0"))
CONFLUENCE_MIN_CEILING = float(os.getenv("CONFLUENCE_MIN_CEILING", "40.0"))


@dataclass
class ThresholdConfig:
    """Current threshold configuration"""
    ml_prob_threshold: float = DEFAULT_ML_THRESHOLD_DEFAULT
    min_score_threshold: float = 55.0
    confluence_min: float = 0.0
    last_updated: datetime = field(default_factory=datetime.utcnow)
    source: str = "default"  # "default", "adaptive", "gemini"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "ml_prob_threshold": self.ml_prob_threshold,
            "min_score_threshold": self.min_score_threshold,
            "confluence_min": self.confluence_min,
            "last_updated": self.last_updated.isoformat(),
            "source": self.source,
        }


class AdaptiveThresholdOptimizer:
    """
    Continuously adapts ML confidence thresholds based on performance metrics.
    
    Key features:
    - Tracks recent outcomes (win rate, avg R)
    - Auto-adjusts thresholds to meet performance targets
    - Falls back to env vars if DB unavailable
    - Integrates with Gemini for strategic suggestions
    """
    
    def __init__(self):
        self._current = ThresholdConfig()
        self._initialized = False
        self._last_analysis: Optional[datetime] = None
        self._analysis_interval_hours = int(os.getenv("THRESHOLD_ANALYSIS_INTERVAL_HOURS", "6"))
        self._min_samples_for_analysis = int(os.getenv("THRESHOLD_MIN_SAMPLES", "20"))
        
    def _load_from_env(self) -> None:
        """Load thresholds from environment variables as baseline"""
        ml_thresh_raw = os.getenv("ML_PROB_THRESHOLD", "").strip()
        if ml_thresh_raw:
            try:
                self._current.ml_prob_threshold = float(ml_thresh_raw)
                self._current.source = "env"
            except ValueError:
                pass
        
        min_score_raw = os.getenv("PREMIUM_SCORE_THRESHOLD", "").strip()
        if min_score_raw:
            try:
                self._current.min_score_threshold = float(min_score_raw)
            except ValueError:
                pass
        confluence_raw = os.getenv("CONFLUENCE_GATE_MIN", "").strip()
        if confluence_raw:
            try:
                self._current.confluence_min = float(confluence_raw)
            except ValueError:
                pass
                
    async def _load_from_db(self) -> bool:
        """Load saved thresholds from runtime_state"""
        try:
            from db.session import get_session
            from sqlalchemy import text
            
            async with get_session() as session:
                row = await session.execute(
                    text("SELECT value FROM runtime_state WHERE key = 'adaptive_thresholds'")
                )
                result = row.first()
                if result and result[0]:
                    data = result[0]
                    if isinstance(data, dict):
                        self._current.ml_prob_threshold = float(
                            data.get("ml_prob_threshold", DEFAULT_ML_THRESHOLD_DEFAULT)
                        )
                        self._current.min_score_threshold = float(
                            data.get("min_score_threshold", self._current.min_score_threshold)
                        )
                        self._current.confluence_min = float(
                            data.get("confluence_min", self._current.confluence_min)
                        )
                        self._current.source = data.get("source", "db")
                        self._initialized = True
                        logger.info(f"[threshold_optimizer] Loaded from DB: {self._current.ml_prob_threshold}")
                        return True
            return False
        except Exception as e:
            logger.debug(f"[threshold_optimizer] DB load failed: {e}")
            return False
            
    async def _save_to_db(self) -> bool:
        """Persist current thresholds to runtime_state"""
        try:
            from db.session import get_session
            from sqlalchemy import text
            
            async with get_session() as session:
                value_json = json.dumps(self._current.to_dict())
                await session.execute(
                    text("""
                        INSERT INTO runtime_state(key, value, updated_at)
                        VALUES ('adaptive_thresholds', CAST(:v AS JSONB), NOW())
                        ON CONFLICT (key) DO UPDATE 
                        SET value = EXCLUDED.value, updated_at = NOW()
                    """),
                    {"v": value_json}
                )
                await session.commit()
            return True
        except Exception as e:
            logger.warning(f"[threshold_optimizer] DB save failed: {e}")
            return False
            
    async def _analyze_performance(self) -> Dict[str, Any]:
        """Analyze recent performance and calculate new thresholds"""
        try:
            from db.session import get_session
            from sqlalchemy import text
            
            # Analyze last 7 days of outcomes
            since = datetime.utcnow() - timedelta(days=7)
            
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
                
                total = int(result[0] or 0) if result else 0
                wins = int(result[1] or 0) if result else 0
                avg_r = float(result[2] or 0.0) if result and result[2] else 0.0
                net_r = float(result[3] or 0.0) if result and result[3] else 0.0
                
                win_rate = wins / max(1, total)

                rejected_count = int(
                    (
                        await session.execute(
                            text(
                                """
                                SELECT COUNT(*) FROM ml_rejected_signals
                                WHERE created_at >= :since
                                """
                            ),
                            {"since": since},
                        )
                    ).scalar()
                    or 0
                )

                recent_score_row = await session.execute(
                    text(
                        """
                        WITH scored AS (
                            SELECT (meta->>'score')::double precision AS score
                            FROM decision_log
                            WHERE created_at >= :since
                              AND meta ? 'score'
                              AND (meta->>'score') ~ '^-?[0-9]+(\\.[0-9]+)?$'
                            UNION ALL
                            SELECT score::double precision AS score
                            FROM signals
                            WHERE created_at >= :since
                              AND score IS NOT NULL
                        )
                        SELECT
                            COUNT(*) AS total,
                            AVG(score) AS avg_score,
                            STDDEV_POP(score) AS std_score,
                            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY score) AS p75_score
                        FROM scored
                        """
                    ),
                    {"since": since},
                )
                recent_score_stats = recent_score_row.first()
                recent_score_total = int(recent_score_stats[0] or 0) if recent_score_stats else 0
                recent_score_mean = float(recent_score_stats[1] or 0.0) if recent_score_stats else 0.0
                recent_score_std = float(recent_score_stats[2] or 0.0) if recent_score_stats and recent_score_stats[2] is not None else 0.0
                recent_score_p75 = float(recent_score_stats[3] or 0.0) if recent_score_stats and recent_score_stats[3] is not None else 0.0

                gemini_row = await session.execute(
                    text("SELECT value FROM runtime_state WHERE key = 'gemini_ml_last_run'")
                )
                gemini_value = gemini_row.first()
                raw_gemini_data = gemini_value[0] if gemini_value else None
                if raw_gemini_data is not None and not isinstance(raw_gemini_data, dict):
                    logger.debug(
                        "[threshold_optimizer] Unexpected gemini_ml_last_run type: %s",
                        type(raw_gemini_data).__name__,
                    )
                gemini_data = raw_gemini_data if isinstance(raw_gemini_data, dict) else {}
                gemini_signal = "neutral"
                received = dict(gemini_data.get("received", {}) or {})
                gemini_ok = bool(gemini_data.get("ok"))
                rejected_or_skipped = int(received.get("rejected_or_skipped") or 0)
                issued = int(received.get("issued") or 0)
                if gemini_ok:
                    if rejected_or_skipped > max(issued, 1):
                        gemini_signal = "tighten"
                    elif issued > 0 and rejected_or_skipped <= max(1, issued // 3):
                        gemini_signal = "loosen"

                return {
                    "total_outcomes": total,
                    "wins": wins,
                    "losses": total - wins,
                    "win_rate": win_rate,
                    "avg_r": avg_r,
                    "net_r": net_r,
                    "rejected_count": rejected_count,
                    "rejected_ratio": rejected_count / max(1, total + rejected_count),
                    "recent_score_total": recent_score_total,
                    "recent_score_mean": recent_score_mean,
                    "recent_score_std": recent_score_std,
                    "recent_score_p75": recent_score_p75,
                    "gemini_signal": gemini_signal,
                }
        except Exception as e:
            logger.warning(f"[threshold_optimizer] Performance analysis failed: {e}")
            return {}
            
    def _calculate_new_threshold(
        self, 
        perf: Dict[str, Any],
        current_threshold: float
    ) -> Tuple[float, str]:
        """
        Calculate optimal threshold based on performance.
        
        Returns (new_threshold, reason)
        """
        if not perf or perf.get("total_outcomes", 0) < self._min_samples_for_analysis:
            return current_threshold, "insufficient_data"
            
        win_rate = perf.get("win_rate", 0.5)
        avg_r = perf.get("avg_r", 0.0)
        
        # Performance scoring
        score = 0.0
        
        # Win rate component (40% weight)
        if win_rate >= TARGET_WIN_RATE:
            score += 0.4
        elif win_rate >= TARGET_WIN_RATE - 0.1:
            score += 0.2
        else:
            score -= 0.2
            
        # Avg R component (40% weight)
        if avg_r >= TARGET_AVG_R:
            score += 0.4
        elif avg_r >= TARGET_AVG_R - 0.5:
            score += 0.2
        else:
            score -= 0.2
            
        # Signal volume component (20% weight) - prefer having some signals
        total_signals = perf.get("total_outcomes", 0)
        if total_signals >= MIN_SIGNALS_PER_CYCLE * 10:  # At least 30 signals in 7 days
            score += 0.2
        elif total_signals < MIN_SIGNALS_PER_CYCLE:
            score -= 0.1

        rejected_ratio = float(perf.get("rejected_ratio", 0.0) or 0.0)
        if rejected_ratio >= 0.60:
            score -= 0.1
        elif rejected_ratio <= 0.25:
            score += 0.05

        gemini_signal = str(perf.get("gemini_signal") or "neutral").lower().strip()
        if gemini_signal == "tighten":
            score -= 0.1
        elif gemini_signal == "loosen":
            score += 0.1
            
        # Adjust threshold based on score
        adjustment = 0.0
        reason = "performance_adjustment"
        
        if score >= 0.8:
            # Excellent performance - slightly loosen threshold for more signals
            adjustment = -0.02
            reason = "excellent_performance_loosen"
        elif score >= 0.4:
            # Good performance - maintain
            adjustment = 0.0
            reason = "good_performance_maintain"
        elif score >= 0.0:
            # Mixed - slightly tighten
            adjustment = 0.02
            reason = "mixed_performance_tighten"
        else:
            # Poor performance - significantly tighten
            adjustment = 0.05
            reason = "poor_performance_tighten"
            
        new_threshold = current_threshold + adjustment
        
        # Clamp to bounds
        new_threshold = max(
            DEFAULT_ML_THRESHOLD_MIN,
            min(DEFAULT_ML_THRESHOLD_MAX, new_threshold)
        )
        
        return new_threshold, reason

    def _calculate_gate_thresholds(
        self,
        perf: Dict[str, Any],
        current_min_score: float,
        current_confluence: float,
    ) -> Tuple[float, float]:
        """Adjust score/confluence gates using ML outcomes plus Gemini signal."""
        if not perf or perf.get("total_outcomes", 0) < self._min_samples_for_analysis:
            return current_min_score, current_confluence

        win_rate = float(perf.get("win_rate", 0.5) or 0.5)
        avg_r = float(perf.get("avg_r", 0.0) or 0.0)
        gemini_signal = str(perf.get("gemini_signal") or "neutral").lower().strip()

        recent_score_total = int(perf.get("recent_score_total", 0) or 0)
        recent_score_mean = float(perf.get("recent_score_mean", 0.0) or 0.0)
        recent_score_std = float(perf.get("recent_score_std", 0.0) or 0.0)
        recent_score_p75 = float(perf.get("recent_score_p75", 0.0) or 0.0)

        score_delta = 0.0
        confluence_delta = 0.0

        if recent_score_total >= self._min_samples_for_analysis:
            # Rolling adaptive gate: mean + 1.0 * std, bounded by safety rails.
            # This is intentionally less aggressive to avoid locking the engine out.
            rolling_threshold = recent_score_mean + (1.0 * recent_score_std)
            if recent_score_p75 > 0:
                rolling_threshold = max(rolling_threshold, recent_score_p75)
            current_min_score = rolling_threshold

        if win_rate < TARGET_WIN_RATE - 0.10 or avg_r < TARGET_AVG_R - 0.5:
            score_delta += 2.0
            confluence_delta += 1.0
        elif win_rate > TARGET_WIN_RATE + 0.05 and avg_r > TARGET_AVG_R:
            score_delta -= 1.0
            confluence_delta -= 0.5

        if gemini_signal == "tighten":
            score_delta += 1.0
            confluence_delta += 0.5
        elif gemini_signal == "loosen":
            score_delta -= 1.0
            confluence_delta -= 0.5

        new_min_score = max(MIN_SCORE_FLOOR, min(MIN_SCORE_CEILING, current_min_score + score_delta))
        new_confluence = max(
            CONFLUENCE_MIN_FLOOR,
            min(CONFLUENCE_MIN_CEILING, current_confluence + confluence_delta),
        )
        return new_min_score, new_confluence
        
    async def analyze_and_adjust(self, force: bool = False) -> ThresholdConfig:
        """
        Main entry point: analyze performance and adjust thresholds if needed.
        
        Args:
            force: Force analysis even if interval not elapsed
            
        Returns:
            Current threshold configuration
        """
        now = datetime.utcnow()
        
        # Check if we need to analyze
        if not force and self._last_analysis:
            hours_since = (now - self._last_analysis).total_seconds() / 3600
            if hours_since < self._analysis_interval_hours:
                return self._current
                
        # Initialize from env/DB on first run
        if not self._initialized:
            self._load_from_env()
            await self._load_from_db()
            self._initialized = True
            
        # Analyze performance
        perf = await self._analyze_performance()
        
        if perf:
            new_thresh, reason = self._calculate_new_threshold(
                perf, 
                self._current.ml_prob_threshold
            )
            new_min_score, new_confluence = self._calculate_gate_thresholds(
                perf,
                self._current.min_score_threshold,
                self._current.confluence_min,
            )

            ml_change = abs(new_thresh - self._current.ml_prob_threshold)
            score_change = abs(new_min_score - self._current.min_score_threshold)
            conf_change = abs(new_confluence - self._current.confluence_min)
            changed = ml_change >= 0.01 or score_change >= 0.5 or conf_change >= 0.5

            if reason != "insufficient_data" and changed:
                self._current.ml_prob_threshold = new_thresh
                self._current.min_score_threshold = new_min_score
                self._current.confluence_min = new_confluence
                self._current.last_updated = now
                gemini_signal = str(perf.get("gemini_signal") or "neutral").lower().strip()
                self._current.source = "adaptive_gemini" if gemini_signal in {"tighten", "loosen"} else "adaptive"
                await self._save_to_db()
                logger.info(
                    "[threshold_optimizer] Adjusted thresholds: ml=%.3f score=%.1f confluence=%.1f "
                    "(win_rate=%.1f%% avg_r=%.2f rejected_ratio=%.1f%% gemini=%s reason=%s)",
                    self._current.ml_prob_threshold,
                    self._current.min_score_threshold,
                    self._current.confluence_min,
                    float(perf.get("win_rate", 0.0) or 0.0) * 100.0,
                    float(perf.get("avg_r", 0.0) or 0.0),
                    float(perf.get("rejected_ratio", 0.0) or 0.0) * 100.0,
                    gemini_signal,
                    reason,
                )
                    
        self._last_analysis = now
        return self._current
        
    def get_threshold(self) -> float:
        """Get current ML probability threshold"""
        return self._current.ml_prob_threshold
        
    def get_config(self) -> ThresholdConfig:
        """Get full threshold configuration"""
        return self._current


# Global singleton instance
_optimizer: Optional[AdaptiveThresholdOptimizer] = None


def get_threshold_optimizer() -> AdaptiveThresholdOptimizer:
    """Get the global optimizer instance"""
    global _optimizer
    if _optimizer is None:
        _optimizer = AdaptiveThresholdOptimizer()
    return _optimizer


async def get_current_threshold() -> float:
    """Convenience function to get current adaptive threshold"""
    optimizer = get_threshold_optimizer()
    return optimizer.get_threshold()


async def refresh_thresholds(force: bool = False) -> ThresholdConfig:
    """Convenience function to refresh and get thresholds"""
    optimizer = get_threshold_optimizer()
    return await optimizer.analyze_and_adjust(force=force)
