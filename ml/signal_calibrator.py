"""
Signal Calibration Service - Dynamic Weight Adjustment

This module provides:
- Track win rate by asset class
- Dynamic weight adjustment
- Performance calibration per asset/timeframe
- Live vs backtest comparison

Usage:
    from ml.signal_calibrator import calibrate_signal_weights
    
    # Calibrate signal based on historical performance
    adjusted_signal = await calibrate_signal_weights(signal)
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from sqlalchemy import Float

logger = logging.getLogger("SignalCalibrator")

# Asset classes
ASSET_CLASSES = {
    "crypto": ["BTC", "ETH", "XRP", "SOL", "ADA", "DOGE", "DOT", "AVAX", "MATIC", "LINK"],
    "forex": ["EUR", "GBP", "USD", "JPY", "AUD", "CAD", "NZD", "CHF"],
    "stock": ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA"],
    "commodity": ["XAU", "XAG", "OIL", "NATGAS", "CORN", "WHEAT"],
}


@dataclass
class AssetClassPerformance:
    """Performance metrics per asset class."""
    asset_class: str
    total_signals: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    avg_r: float = 0.0
    expectancy: float = 0.0
    last_updated: Optional[datetime] = None


class SignalCalibrator:
    """
    Dynamic signal weight calibration based on historical performance.
    
    Tracks win rate and expectancy by asset class and adjusts signal
    weights dynamically. Also compares backtest vs live performance to
    identify overfitting.
    """
    
    def __init__(self):
        self._performance_cache: Dict[str, AssetClassPerformance] = {}
        self._lookback_days = 30
    
    async def calibrate_signal_weights(
        self,
        signal: Dict[str, Any],
        use_ml_adjustment: bool = True
    ) -> Dict[str, Any]:
        """
        Calibrate signal weights based on asset class performance.
        
        Args:
            signal: Signal dict
            use_ml_adjustment: Whether to apply ML-based adjustment
            
        Returns:
            Signal with adjusted score, weight, and metadata
        """
        calibrated = signal.copy()
        
        asset = signal.get("asset", "")
        asset_class = self._get_asset_class(asset)
        
        # Get performance for asset class
        perf = await self._get_asset_class_performance(asset_class)
        
        if perf and perf.total_signals >= 10:
            # Apply performance-based adjustment
            # If win_rate > 50%, boost the score slightly
            # If win_rate < 40%, reduce the score
            adjustment_factor = 1.0
            
            if perf.win_rate > 55:
                adjustment_factor = 1.1  # 10% boost
            elif perf.win_rate < 45:
                adjustment_factor = 0.9  # 10% penalty
            
            # Apply to score
            original_score = signal.get("score", 0)
            calibrated["score"] = original_score * adjustment_factor
            calibrated["performance_adjustment"] = {
                "factor": adjustment_factor,
                "asset_class": asset_class,
                "win_rate": perf.win_rate,
                "original_score": original_score,
            }
        else:
            calibrated["performance_adjustment"] = None
        
        return calibrated
    
    async def record_outcome(
        self,
        signal_id: str,
        asset: str,
        outcome_status: str,
        r_multiple: float,
        exited_at: datetime
    ) -> bool:
        """
        Record signal outcome for calibration.
        
        Args:
            signal_id: Signal ID
            asset: Asset symbol
            outcome_status: "win" or "loss"
            r_multiple: R multiple achieved
            exited_at: Exit timestamp
        """
        try:
            asset_class = self._get_asset_class(asset)
            
            # Update performance
            current = await self._get_asset_class_performance(asset_class)
            
            if not current:
                current = AssetClassPerformance(asset_class=asset_class)
            
            current.total_signals += 1
            
            if outcome_status in ("win", "tp", "partial"):
                current.wins += 1
            else:
                current.losses += 1
            
            # Update win rate
            current.win_rate = (current.wins / current.total_signals) * 100
            
            # Update average R
            if current.total_signals > 1:
                current.avg_r = (
                    (current.avg_r * (current.total_signals - 1) + r_multiple)
                    / current.total_signals
                )
            else:
                current.avg_r = r_multiple
            
            # Update expectancy
            win_pct = current.win_rate / 100
            avg_win_r = current.avg_r if current.wins > 0 else 0
            avg_loss_r = abs(current.avg_r) if current.losses > 0 else 1.0
            
            current.expectancy = (win_pct * avg_win_r) - ((1 - win_pct) * avg_loss_r)
            current.last_updated = datetime.utcnow()
            
            # Save to cache
            self._performance_cache[asset_class] = current
            
            # Persist to DB
            await self._save_performance(current)
            
            logger.info(f"[SignalCalibrator] Recorded outcome for {asset_class}: win_rate={current.win_rate:.1f}%")
            return True
            
        except Exception as e:
            logger.error(f"[SignalCalibrator] Record outcome error: {e}")
            return False
    
    async def get_asset_class_performance(
        self,
        asset_class: str
    ) -> Optional[AssetClassPerformance]:
        """Get performance for an asset class."""
        return await self._get_asset_class_performance(asset_class)
    
    async def get_all_performance(self) -> Dict[str, AssetClassPerformance]:
        """Get performance for all asset classes."""
        results = {}
        
        for asset_class in ASSET_CLASSES.keys():
            perf = await self._get_asset_class_performance(asset_class)
            if perf:
                results[asset_class] = perf
        
        return results
    
    async def compare_backtest_vs_live(
        self,
        strategy_name: str,
        lookback_days: int = 30
    ) -> Dict[str, Any]:
        """
        Compare backtest vs live performance to identify overfitting.
        
        Args:
            strategy_name: Strategy to analyze
            lookback_days: Days to look back
            
        Returns:
            Dict with comparison metrics
        """
        try:
            from db.session import get_session
            from db.models import Outcome, Signal
            from sqlalchemy import select, func
            from utils.timeutils import now_utc_naive
            
            now = now_utc_naive()
            cutoff = now - timedelta(days=lookback_days)
            
            # Get live outcomes
            async with get_session() as session:
                # Count live signals and outcomes
                result = await session.execute(
                    select(
                        func.count(Outcome.id),
                        func.sum(func.cast(Outcome.r_multiple, Float)),
                        func.avg(func.cast(Outcome.r_multiple, Float))
                    ).join(
                        Signal, Outcome.signal_id == Signal.signal_id
                    ).where(
                        Signal.strategy_name == strategy_name,
                        Signal.created_at >= cutoff
                    )
                )
                row = result.fetchone()
                
                live_trades = row[0] if row else 0
                live_pnl = float(row[1] or 0)
                live_avg_r = float(row[2] or 0)
                
                # Note: Real backtest comparison would need stored backtest results
                # For now, return live metrics with placeholder comparison
                return {
                    "strategy": strategy_name,
                    "period_days": lookback_days,
                    "live_trades": live_trades,
                    "live_pnl": live_pnl,
                    "live_avg_r": live_avg_r,
                    "backtest_trades": None,  # Would need backtest storage
                    "backtest_avg_r": None,
                    "degradation": None,  # Would be live - backtest
                    "overfitting_risk": "unknown",
                }
            
        except Exception as e:
            logger.error(f"[SignalCalibrator] Compare error: {e}")
            return {"error": str(e)}
    
    def _get_asset_class(self, asset: str) -> str:
        """Determine asset class from symbol."""
        asset_upper = asset.upper()
        
        for class_name, assets in ASSET_CLASSES.items():
            for a in assets:
                if asset_upper.startswith(a):
                    return class_name
        
        return "crypto"  # Default to crypto
    
    async def _get_asset_class_performance(
        self,
        asset_class: str
    ) -> Optional[AssetClassPerformance]:
        """Get or compute performance for asset class."""
        # Check cache first
        if asset_class in self._performance_cache:
            return self._performance_cache[asset_class]
        
        # Load from DB
        try:
            from db.session import get_session
            from db.models import RuntimeState
            from sqlalchemy import select
            
            async with get_session() as session:
                result = await session.execute(
                    select(RuntimeState).where(
                        RuntimeState.key == f"perf:{asset_class}"
                    )
                )
                state = result.first()
                if state:
                    data = state.value
                    perf = AssetClassPerformance(
                        asset_class=data.get("asset_class", asset_class),
                        total_signals=data.get("total_signals", 0),
                        wins=data.get("wins", 0),
                        losses=data.get("losses", 0),
                        win_rate=data.get("win_rate", 0),
                        avg_r=data.get("avg_r", 0),
                        expectancy=data.get("expectancy", 0),
                    )
                    self._performance_cache[asset_class] = perf
                    return perf
                    
        except Exception as e:
            logger.debug(f"[SignalCalibrator] Load perf error: {e}")
        
        return None
    
    async def _save_performance(self, perf: AssetClassPerformance) -> bool:
        """Save performance to DB."""
        try:
            from db.session import get_session
            from db.models import RuntimeState
            
            async with get_session() as session:
                state = RuntimeState(
                    key=f"perf:{perf.asset_class}",
                    value={
                        "asset_class": perf.asset_class,
                        "total_signals": perf.total_signals,
                        "wins": perf.wins,
                        "losses": perf.losses,
                        "win_rate": perf.win_rate,
                        "avg_r": perf.avg_r,
                        "expectancy": perf.expectancy,
                        "last_updated": perf.last_updated.isoformat() if perf.last_updated else None,
                    },
                )
                session.add(state)
                await session.commit()
                return True
                
        except Exception as e:
            logger.error(f"[SignalCalibrator] Save perf error: {e}")
            return False


# Convenience functions
async def calibrate_signal(
    signal: Dict[str, Any]
) -> Dict[str, Any]:
    """Calibrate signal weights."""
    calibrator = SignalCalibrator()
    return await calibrator.calibrate_signal_weights(signal)


async def record_signal_outcome(
    signal_id: str,
    asset: str,
    outcome_status: str,
    r_multiple: float
) -> bool:
    """Record signal outcome."""
    calibrator = SignalCalibrator()
    return await calibrator.record_outcome(
        signal_id, asset, outcome_status, r_multiple, datetime.utcnow()
    )


if __name__ == "__main__":
    # Quick test
    import asyncio
    
    async def test():
        print("Testing Signal Calibrator...")
        
        test_signal = {
            "signal_id": "test_123",
            "asset": "BTCUSDT",
            "direction": "long",
            "score": 75.0,
        }
        
        calibrated = await calibrate_signal(test_signal)
        print(f"Calibrated: {calibrated}")
    
    asyncio.run(test())
