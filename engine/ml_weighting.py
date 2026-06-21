"""
ML Weighting Layer
Phase 3.2 - Self-adjusting strategy weights based on performance

Stores: Strategy, Asset, Timeframe, Regime, Result
Self-adjusts based on historical performance
"""

import logging
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# Performance lookback windows (days)
LOOKBACK_WINDOWS = [7, 14, 30, 90]


@dataclass
class StrategyRecord:
    """Single strategy outcome record."""
    strategy: str
    asset_class: str
    timeframe: str
    regime: str
    result: str  # 'win', 'loss', 'breakeven'
    pnl_pct: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass  
class StrategyPerformance:
    """Aggregated strategy performance."""
    strategy: str
    asset_class: str
    timeframe: str
    regime: str
    
    total: int = 0
    wins: int = 0
    losses: int = 0
    
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    win_rate: float = 0.0
    
    expectancy: float = 0.0  # win_rate * avg_win - (1-win_rate) * avg_loss
    
    last_7d: int = 0
    last_14d: int = 0
    last_30d: int = 0
    last_90d: int = 0
    
    adjusted_weight: float = 0.5  # ML-adjusted weight (0.0-1.0)


class MLWeightingLayer:
    """ML-powered strategy weighting system."""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize ML weighting layer.
        
        Args:
            db_path: Optional path to JSON file for persistence
        """
        self.db_path = db_path or os.getenv("ML_WEIGHTING_DB", "data/ml_weights.json")
        self.records: List[StrategyRecord] = []
        self._load_records()
    
    def _load_records(self) -> None:
        """Load records from persistent storage."""
        if not os.path.exists(self.db_path):
            return
            
        try:
            with open(self.db_path, 'r') as f:
                data = json.load(f)
                
            for item in data.get('records', []):
                ts = item.get('timestamp')
                if ts:
                    try:
                        ts = datetime.fromisoformat(ts)
                    except Exception:
                        ts = datetime.now(timezone.utc)
                else:
                    ts = datetime.now(timezone.utc)
                    
                self.records.append(StrategyRecord(
                    strategy=item.get('strategy', ''),
                    asset_class=item.get('asset_class', ''),
                    timeframe=item.get('timeframe', ''),
                    regime=item.get('regime', ''),
                    result=item.get('result', ''),
                    pnl_pct=float(item.get('pnl_pct', 0)),
                    timestamp=ts,
                ))
                
            logger.info(f"[ml_weighting] Loaded {len(self.records)} records")
            
        except Exception as e:
            logger.warning(f"[ml_weighting] Load failed: {e}")
    
    def _save_records(self) -> None:
        """Save records to persistent storage."""
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            data = {
                'records': [
                    {
                        'strategy': r.strategy,
                        'asset_class': r.asset_class,
                        'timeframe': r.timeframe,
                        'regime': r.regime,
                        'result': r.result,
                        'pnl_pct': r.pnl_pct,
                        'timestamp': r.timestamp.isoformat(),
                    }
                    for r in self.records
                ],
                'updated_at': datetime.now(timezone.utc).isoformat(),
            }
            
            with open(self.db_path, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.warning(f"[ml_weighting] Save failed: {e}")
    
    def record_outcome(
        self,
        strategy: str,
        asset_class: str,
        timeframe: str,
        regime: str,
        result: str,
        pnl_pct: float,
    ) -> None:
        """Record a strategy outcome."""
        record = StrategyRecord(
            strategy=strategy,
            asset_class=asset_class,
            timeframe=timeframe,
            regime=regime,
            result=result,
            pnl_pct=pnl_pct,
        )
        
        self.records.append(record)
        
        # Keep bounded
        max_records = int(os.getenv("ML_MAX_RECORDS", "10000"))
        if len(self.records) > max_records:
            self.records = self.records[-max_records:]
        
        # Save periodically (every 100 records)
        if len(self.records) % 100 == 0:
            self._save_records()
    
    def get_performance(
        self,
        strategy: str,
        asset_class: str,
        timeframe: str,
        regime: str,
    ) -> StrategyPerformance:
        """Get aggregated performance for a strategy combo."""
        now = datetime.now(timezone.utc)
        
        # Filter matching records
        matches = [
            r for r in self.records
            if r.strategy == strategy
            and r.asset_class == asset_class
            and r.timeframe == timeframe
            and r.regime == regime
        ]
        
        if not matches:
            return StrategyPerformance(
                strategy=strategy,
                asset_class=asset_class,
                timeframe=timeframe,
                regime=regime,
            )
        
        # Calculate basic stats
        total = len(matches)
        wins = sum(1 for r in matches if r.result == 'win')
        losses = sum(1 for r in matches if r.result == 'loss')
        
        wins_list = [r.pnl_pct for r in matches if r.result == 'win']
        losses_list = [r.pnl_pct for r in matches if r.result == 'loss']
        
        avg_win = sum(wins_list) / len(wins_list) if wins_list else 0
        avg_loss = abs(sum(losses_list) / len(losses_list)) if losses_list else 0
        
        win_rate = (wins / total * 100) if total > 0 else 0
        
        # Expectancy
        expectancy = 0.0
        if total > 0:
            expectancy = (wins / total) * avg_win - (losses / total) * avg_loss
        
        # Time-bounded counts
        last_7d = self._count_recent(matches, now, 7)
        last_14d = self._count_recent(matches, now, 14)
        last_30d = self._count_recent(matches, now, 30)
        last_90d = self._count_recent(matches, now, 90)
        
        # Adjusted weight based on recent performance
        adjusted_weight = self._calculate_adjusted_weight(
            matches=matches,
            now=now,
            base_win_rate=win_rate,
            expectancy=expectancy,
        )
        
        return StrategyPerformance(
            strategy=strategy,
            asset_class=asset_class,
            timeframe=timeframe,
            regime=regime,
            total=total,
            wins=wins,
            losses=losses,
            avg_win_pct=avg_win,
            avg_loss_pct=avg_loss,
            win_rate=win_rate,
            expectancy=expectancy,
            last_7d=last_7d,
            last_14d=last_14d,
            last_30d=last_30d,
            last_90d=last_90d,
            adjusted_weight=adjusted_weight,
        )
    
    def _count_recent(
        self,
        records: List[StrategyRecord],
        now: datetime,
        days: int,
    ) -> int:
        """Count records within last N days."""
        cutoff = now - timedelta(days=days)
        return sum(1 for r in records if r.timestamp >= cutoff)
    
    def _calculate_adjusted_weight(
        self,
        matches: List[StrategyRecord],
        now: datetime,
        base_win_rate: float,
        expectancy: float,
    ) -> float:
        """
        Calculate ML-adjusted weight (0.0-1.0).
        
        Based on:
        - Recent win rate (last 7d)
        - Trend (7d vs 30d)
        - Expectancy
        - Sample size confidence
        """
        # Recent window
        cutoff_7d = now - timedelta(days=7)
        recent = [r for r in matches if r.timestamp >= cutoff_7d]
        
        if not recent:
            return 0.5  # No data - neutral
        
        # Recent win rate
        recent_wins = sum(1 for r in recent if r.result == 'win')
        recent_rate = (recent_wins / len(recent) * 100) if recent else 0
        
        # Sample size confidence
        sample_size = len(recent)
        confidence = min(sample_size / 10, 1.0)  # 10 trades = full confidence
        
        # Base weight from win rate
        weight = base_win_rate / 100  # 0.0-1.0
        
        # Recency adjustment
        if recent_rate > base_win_rate + 10:
            weight += 0.15  # Improving
        elif recent_rate < base_win_rate - 10:
            weight -= 0.15  # Declining
            
        # Expectancy bonus/penalty
        if expectancy > 1.0:
            weight += 0.1  # High expectancy
        elif expectancy < 0:
            weight -= 0.1  # Negative expectancy
            
        # Apply confidence
        weight = 0.5 + (weight - 0.5) * confidence
        
        # Clamp
        return max(0.0, min(1.0, weight))
    
    def get_weights_for_orchestrator(
        self,
        asset_class: str,
        timeframe: str,
        regime: str,
    ) -> Dict[str, float]:
        """
        Get strategy weights for the StrategyOrchestrator.
        
        Returns: Dict[str, float] - strategy -> adjusted weight
        """
        from engine.strategy_orchestrator import STRATEGY_CONDITIONS
        
        weights: Dict[str, float] = {}
        
        for strategy in STRATEGY_CONDITIONS.keys():
            perf = self.get_performance(
                strategy=strategy,
                asset_class=asset_class,
                timeframe=timeframe,
                regime=regime,
            )
            
            if perf.total >= 3:  # Minimum sample
                weights[strategy] = perf.adjusted_weight
            else:
                weights[strategy] = 0.5  # Default for insufficient data
        
        return weights
    
    def get_strategy_recommendation(
        self,
        asset_class: str,
        timeframe: str,
        regime: str,
    ) -> Tuple[Optional[str], str]:
        """
        Get the recommended strategy with explanation.
        
        Returns: (strategy_name, explanation)
        """
        weights = self.get_weights_for_orchestrator(
            asset_class=asset_class,
            timeframe=timeframe,
            regime=regime,
        )
        
        if not weights:
            return None, "insufficient data"
        
        # Sort by weight
        sorted_strategies = sorted(weights.items(), key=lambda x: x[1], reverse=True)
        
        best_strategy, best_weight = sorted_strategies[0]
        
        if best_weight >= 0.6:
            expl = f"strong performer (weight={best_weight:.2f})"
        elif best_weight >= 0.4:
            expl = f"neutral (weight={best_weight:.2f})"
        else:
            expl = f"underperforming (weight={best_weight:.2f})"
        
        return best_strategy, expl
    
    def get_all_performances(self) -> List[StrategyPerformance]:
        """Get all strategy performances."""
        from engine.strategy_orchestrator import STRATEGY_CONDITIONS
        
        performances: List[StrategyPerformance] = []
        
        seen = set()
        
        for strategy in STRATEGY_CONDITIONS.keys():
            for asset_class in ['crypto', 'forex_major', 'indices', 'commodities']:
                for timeframe in ['15m', '1h', '4h']:
                    for regime in ['TRENDING', 'RANGING', 'VOLATILE']:
                        key = (strategy, asset_class, timeframe, regime)
                        if key in seen:
                            continue
                        seen.add(key)
                        
                        perf = self.get_performance(
                            strategy=strategy,
                            asset_class=asset_class,
                            timeframe=timeframe,
                            regime=regime,
                        )
                        
                        if perf.total > 0:
                            performances.append(perf)
        
        # Sort by expectancy descending
        performances.sort(key=lambda x: x.expectancy, reverse=True)
        
        return performances


# Singleton instance
_layer: Optional[MLWeightingLayer] = None


def get_ml_weighting_layer() -> MLWeightingLayer:
    """Get the global ML weighting layer."""
    global _layer
    if _layer is None:
        _layer = MLWeightingLayer()
    return _layer


def record_strategy_outcome(
    strategy: str,
    asset_class: str,
    timeframe: str,
    regime: str,
    result: str,
    pnl_pct: float,
) -> None:
    """Convenience function to record outcome."""
    get_ml_weighting_layer().record_outcome(
        strategy=strategy,
        asset_class=asset_class,
        timeframe=timeframe,
        regime=regime,
        result=result,
        pnl_pct=pnl_pct,
    )


def get_strategy_weights(
    asset_class: str,
    timeframe: str,
    regime: str,
) -> Dict[str, float]:
    """Convenience function to get adjusted weights."""
    return get_ml_weighting_layer().get_weights_for_orchestrator(
        asset_class=asset_class,
        timeframe=timeframe,
        regime=regime,
    )


def get_recommended_strategy(
    asset_class: str,
    timeframe: str,
    regime: str,
) -> Tuple[Optional[str], str]:
    """Convenience function to get recommendation."""
    return get_ml_weighting_layer().get_strategy_recommendation(
        asset_class=asset_class,
        timeframe=timeframe,
        regime=regime,
    )
