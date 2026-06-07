"""
Auto-Optimizer - Self-Healing Risk Management

This module analyzes historical MAE (Maximum Adverse Excursion) data from closed trades
to automatically optimize the system's Stop Loss parameter.

The Concept: A background worker runs weekly, analyzes MAE of winning trades,
and if findings show the current SL is too conservative, it tightens it
to maximize Risk/Reward ratio while maintaining safety.

Usage:
    from engine.auto_optimizer import AutoOptimizerRunner
    
    runner = AutoOptimizerRunner()
    result = await runner.run_optimization()
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("AutoOptimizer")

# Feature toggle
AUTO_OPTIMIZER_ENABLED = os.getenv("AUTO_OPTIMIZER_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}

# Configuration
MIN_WINNING_TRADES = int(os.getenv("AUTO_OPT_MIN_TRADES", "50"))
DEFAULT_TARGET_PERCENTILE = float(os.getenv("AUTO_OPT_TARGET_PERCENTILE", "0.90"))
OPTIMIZATION_INTERVAL_HOURS = int(os.getenv("AUTO_OPT_INTERVAL_HOURS", "168"))  # Weekly


@dataclass
class OptimizationResult:
    """Result of optimization analysis."""
    recommended_sl: float
    current_sl: float
    confidence: float
    analysis_trade_count: int
    reasoning: str


class AutoOptimizerRunner:
    """
    Runs optimization analysis on historical trade data.
    
    Analyzes MAE (Maximum Adverse Excursion) of winning trades to
    determine if the Stop Loss can be tightened for better risk/reward.
    """
    
    def __init__(
        self,
        target_percentile: float = DEFAULT_TARGET_PERCENTILE,
    ):
        self.target_percentile = target_percentile
    
    async def run_optimization(self) -> Optional[OptimizationResult]:
        """
        Run the optimization analysis.
        
        Returns:
            OptimizationResult or None if insufficient data
        """
        if not AUTO_OPTIMIZER_ENABLED:
            return None
        
        try:
            # Get closed trades from database
            trades = await self._fetch_closed_trades()
            
            if not trades or len(trades) < MIN_WINNING_TRADES:
                logger.info(f"[auto_opt] Insufficient trades: {len(trades) or 0} < {MIN_WINNING_TRADES}")
                return None
            
            # Filter for winning trades with MAE data
            winning_trades = [
                t for t in trades
                if self._is_winning_trade(t) and self._has_mae_data(t)
            ]
            
            if len(winning_trades) < MIN_WINNING_TRADES:
                logger.info(f"[auto_opt] Insufficient winning trades: {len(winning_trades)} < {MIN_WINNING_TRADES}")
                return None
            
            # Analyze MAE distribution
            result = await self._analyze_mae(winning_trades)
            
            return result
            
        except Exception as e:
            logger.error(f"[auto_opt] Optimization failed: {e}")
            return None
    
    async def _fetch_closed_trades(self) -> list:
        """Fetch closed trades from database."""
        try:
            from db.session import get_session
            from db.models import Trade
            from sqlalchemy import select
            
            async with get_session() as session:
                # Get last 30 days of closed trades
                cutoff = datetime.utcnow() - timedelta(days=30)
                result = await session.execute(
                    select(Trade).where(
                        Trade.status == "closed",
                        Trade.exit_time >= cutoff,
                    )
                )
                return list(result.scalars().all())
                
        except Exception as e:
            logger.debug(f"[auto_opt] Failed to fetch trades: {e}")
            return []
    
    def _is_winning_trade(self, trade) -> bool:
        """Check if trade was profitable."""
        try:
            pnl = getattr(trade, "pnl", None) or getattr(trade, "pnl_pct", None)
            return pnl is not None and float(pnl) > 0
        except Exception:
            return False
    
    def _has_mae_data(self, trade) -> bool:
        """Check if trade has MAE data."""
        try:
            mae = getattr(trade, "mae_pct", None)
            return mae is not None
        except Exception:
            return False
    
    async def _analyze_mae(
        self,
        winning_trades: list,
    ) -> OptimizationResult:
        """
        Analyze MAE distribution to recommend optimal SL.
        
        Uses percentile-based approach: finds the MAE that covers
        X% of winning trades (e.g., 90% = only 10% would have hit SL).
        """
        import numpy as np
        
        # Extract MAE values (typically negative)
        mae_values = []
        for trade in winning_trades:
            try:
                mae = float(getattr(trade, "mae_pct", 0) or 0)
                if mae != 0:
                    mae_values.append(abs(mae))  # Use absolute for analysis
            except Exception:
                continue
        
        if not mae_values:
            return OptimizationResult(
                recommended_sl=-2.0,
                current_sl=-2.0,
                confidence=0.0,
                analysis_trade_count=0,
                reasoning="No MAE data available",
            )
        
        # Calculate optimal SL based on target percentile
        optimal_mae = np.percentile(mae_values, self.target_percentile * 100)
        
        # Add small buffer for market noise
        recommended_sl = -(abs(optimal_mae) + 0.1)
        
        # Get current SL from config
        current_sl = float(os.getenv("STOP_LOSS_PCT", "-2.0"))
        
        # Calculate confidence based on sample size
        confidence = min(1.0, len(winning_trades) / 200.0)
        
        reasoning = (
            f"Based on {len(winning_trades)} winning trades, "
            f"{self.target_percentile*100:.0f}% survived a -{abs(optimal_mae):.2f}% drawdown. "
            f"Recommended SL: {recommended_sl:.2f}%"
        )
        
        logger.info(f"[auto_opt] {reasoning}")
        
        return OptimizationResult(
            recommended_sl=recommended_sl,
            current_sl=current_sl,
            confidence=confidence,
            analysis_trade_count=len(winning_trades),
            reasoning=reasoning,
        )
    
    async def apply_recommended_sl(self, result: OptimizationResult) -> bool:
        """
        Apply recommended SL to system config.
        
        Args:
            result: OptimizationResult from run_optimization
            
        Returns:
            True if successfully applied
        """
        if not result or result.confidence < 0.7:
            logger.info(f"[auto_opt] Confidence too low: {result.confidence if result else 0}")
            return False
        
        try:
            # Update environment variable (would need to persist to DB in production)
            new_sl = str(result.recommended_sl)
            os.environ["STOP_LOSS_PCT"] = new_sl
            
            logger.warning(f"[auto_opt] APPLIED: New SL = {new_sl}%")
            
            return True
            
        except Exception as e:
            logger.error(f"[auto_opt] Failed to apply SL: {e}")
            return False


# Default instance
_default_runner = None


def get_runner() -> AutoOptimizerRunner:
    """Get default optimizer runner instance."""
    global _default_runner
    if _default_runner is None:
        _default_runner = AutoOptimizerRunner()
    return _default_runner


async def run_optimization() -> Optional[OptimizationResult]:
    """Convenience function to run optimization."""
    runner = get_runner()
    return await runner.run_optimization()
