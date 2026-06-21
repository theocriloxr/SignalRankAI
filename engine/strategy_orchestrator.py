"""
Strategy Orchestrator
Phase 3.1 - Dynamic Strategy Selection

Inputs: Asset, Timeframe, Volatility, Regime, Session, Spread
Output: Strategy Weighting + Selection
"""

import logging
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Strategy definitions with conditions
STRATEGY_CONDITIONS = {
    'breakout_momentum': {
        'regimes': ['TRENDING', 'VOLATILE'],
        'min_atr_pct': 1.0,
        'max_atr_pct': None,
        'sessions': ['asian', 'london', 'newyork'],
        'best_timeframes': ['15m', '1h', '4h'],
    },
    'mean_reversion': {
        'regimes': ['RANGING', 'NEUTRAL'],
        'min_atr_pct': 0.3,
        'max_atr_pct': 2.0,
        'sessions': ['asian', 'london'],
        'best_timeframes': ['15m', '30m', '1h'],
    },
    'trend_continuation': {
        'regimes': ['TRENDING'],
        'min_atr_pct': 0.5,
        'max_atr_pct': 4.0,
        'sessions': ['london', 'newyork'],
        'best_timeframes': ['1h', '4h', '1d'],
    },
    'breakout_reversal': {
        'regimes': ['VOLATILE', 'TRENDING'],
        'min_atr_pct': 2.0,
        'max_atr_pct': None,
        'sessions': ['newyork'],
        'best_timeframes': ['5m', '15m', '1h'],
    },
    'scalp_momentum': {
        'regimes': ['TRENDING', 'VOLATILE'],
        'min_atr_pct': 0.5,
        'max_atr_pct': 2.0,
        'sessions': ['london', 'newyork'],
        'best_timeframes': ['1m', '5m', '15m'],
    },
    'swing_formation': {
        'regimes': ['TRENDING', 'RANGING'],
        'min_atr_pct': 0.8,
        'max_atr_pct': None,
        'sessions': ['london', 'newyork', 'asian'],
        'best_timeframes': ['4h', '1d', '1w'],
    },
}


# Asset class mappings
ASSET_CLASSES = {
    'crypto': ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'DOGE', 'DOT', 'AVAX', 'MATIC', 'LINK', 'UNI'],
    'forex_major': ['EUR', 'USD', 'GBP', 'JPY', 'AUD', 'CAD', 'CHF', 'NZD'],
    'forex_jpy': ['JPY', 'GBP/JPY', 'EUR/JPY', 'AUD/JPY', 'NZD/JPY'],
    'forex_comd': ['EUR/GBP', 'EUR/AUD', 'GBP/AUD'],
    'indices': ['US30', 'US500', 'NAS100', 'GER40', 'UK100', 'JPN225'],
    'commodities': ['XAU', 'XAG', 'OIL', 'NATGAS'],
}


@dataclass
class StrategyWeights:
    strategy: str
    weight: float
    reason: str
    confidence: float


class StrategyOrchestrator:
    """Select and weight strategies based on market conditions."""
    
    def __init__(self):
        self.strategy_history: Dict[str, List[Dict]] = {}
        
    def get_strategy_weights(
        self,
        asset: str,
        timeframe: str,
        regime: str,
        session: str,
        atr_pct: float,
        spread: Optional[float] = None,
    ) -> List[StrategyWeights]:
        """
        Get weighted strategy recommendations.
        
        Args:
            asset: Trading symbol (e.g., 'BTCUSDT')
            timeframe: Timeframe (e.g., '1h', '15m')
            regime: Market regime from regime.py
            session: Trading session ('asian', 'london', 'newyork')
            atr_pct: ATR as percentage of price
            spread: Symbol spread (optional)
            
        Returns:
            List of StrategyWeights with recommendations
        """
        asset_class = self._get_asset_class(asset)
        weights: List[StrategyWeights] = []
        
        for strategy_name, conditions in STRATEGY_CONDITIONS.items():
            score = self._calculate_strategy_score(
                strategy_name=strategy_name,
                conditions=conditions,
                asset_class=asset_class,
                timeframe=timeframe,
                regime=regime,
                session=session,
                atr_pct=atr_pct,
                spread=spread,
            )
            
            if score['weight'] > 0:
                weights.append(StrategyWeights(
                    strategy=strategy_name,
                    weight=score['weight'],
                    reason=score['reason'],
                    confidence=score['confidence'],
                ))
        
        # Sort by weight descending
        weights.sort(key=lambda x: x.weight, reverse=True)
        
        return weights[:5]  # Top 5 strategies
    
    def _get_asset_class(self, asset: str) -> str:
        """Determine asset class."""
        asset_upper = asset.upper().replace('USDT', '').replace('USD', '').replace('/', '')
        
        for class_name, symbols in ASSET_CLASSES.items():
            if any(s in asset_upper for s in symbols):
                return class_name
                
        return 'crypto' if len(asset_upper) <= 5 else 'forex_major'
    
    def _calculate_strategy_score(
        self,
        strategy_name: str,
        conditions: Dict,
        asset_class: str,
        timeframe: str,
        regime: str,
        session: str,
        atr_pct: float,
        spread: Optional[float],
    ) -> Dict:
        """Calculate strategy suitability score."""
        score = {'weight': 0.0, 'reason': '', 'confidence': 0.0}
        
        try:
            # Regime check
            valid_regimes = conditions.get('regimes', [])
            regime_match = regime in valid_regimes
            if not regime_match:
                return score
                
            # Timeframe check
            tf_match = timeframe in conditions.get('best_timeframes', [])
            
            # Session check
            session_match = session in conditions.get('sessions', ['any'])
            
            # ATR check
            min_atr = conditions.get('min_atr_pct', 0)
            max_atr = conditions.get('max_atr_pct', 999)
            atr_valid = min_atr <= atr_pct <= max_atr
            
            # Calculate weights
            base_weight = 0.3
            if regime_match:
                base_weight += 0.3
            if tf_match:
                base_weight += 0.2
            if session_match:
                base_weight += 0.1
            if atr_valid:
                base_weight += 0.1
                
            # Asset class adjustments
            if asset_class == 'crypto' and strategy_name in ['breakout_momentum', 'scalp_momentum']:
                base_weight += 0.1
            elif asset_class in ['forex_major', 'forex_jpy'] and strategy_name in ['trend_continuation', 'mean_reversion']:
                base_weight += 0.1
            elif asset_class == 'indices' and strategy_name in ['breakout_reversal', 'swing_formation']:
                base_weight += 0.1
                
            # Spread penalty for forex
            if spread and spread > 3.0 and asset_class in ['forex_major', 'forex_jpy']:
                base_weight -= 0.2
                
            score['weight'] = max(0.0, base_weight)
            score['confidence'] = min(score['weight'] * 100, 100)
            
            # Build reason
            reasons = []
            if regime_match:
                reasons.append(f"regime={regime}")
            if tf_match:
                reasons.append(f"tf={timeframe}")
            if session_match:
                reasons.append(f"session={session}")
            score['reason'] = ', '.join(reasons) if reasons else 'baseline'
            
        except Exception as e:
            logger.debug(f"[strategy_orchestrator] score calc error: {e}")
            
        return score
    
    def get_best_strategy(
        self,
        asset: str,
        timeframe: str,
        regime: str,
        session: str,
        atr_pct: float,
        spread: Optional[float] = None,
    ) -> Tuple[Optional[str], str]:
        """Get the single best strategy with reasoning."""
        weights = self.get_strategy_weights(
            asset=asset,
            timeframe=timeframe,
            regime=regime,
            session=session,
            atr_pct=atr_pct,
            spread=spread,
        )
        
        if not weights:
            return None, "no suitable strategy"
        
        best = weights[0]
        return best.strategy, best.reason
    
    def record_strategy_result(
        self,
        strategy: str,
        asset: str,
        timeframe: str,
        result: str,  # 'win', 'loss', 'breakeven'
        pnl_pct: float,
    ) -> None:
        """Record strategy outcome for self-adjustment."""
        key = f"{strategy}:{asset}:{timeframe}"
        
        if key not in self.strategy_history:
            self.strategy_history[key] = []
        
        self.strategy_history[key].append({
            'result': result,
            'pnl_pct': pnl_pct,
        })
        
        # Keep history bounded
        if len(self.strategy_history[key]) > 100:
            self.strategy_history[key] = self.strategy_history[key][-100:]
    
    def get_strategy_stats(self, strategy: str) -> Dict:
        """Get strategy historical performance."""
        history = [
            h for k, h in self.strategy_history.items() 
            if k.startswith(strategy + ':')
        ]
        
        if not history:
            return {'total': 0, 'win_rate': 0.0, 'avg_pnl': 0.0}
        
        flat = [item for h in history for item in h]
        wins = sum(1 for i in flat if i['result'] == 'win')
        total = len(flat)
        
        return {
            'total': total,
            'win_rate': (wins / total * 100) if total > 0 else 0.0,
            'avg_pnl': sum(i['pnl_pct'] for i in flat) / total if total > 0 else 0.0,
        }


def get_current_session() -> str:
    """Determine current trading session."""
    from datetime import datetime
    
    utc_hour = datetime.utcnow().hour
    
    # Asian session: 0-8 UTC
    if 0 <= utc_hour < 8:
        return 'asian'
    # London session: 8-16 UTC
    elif 8 <= utc_hour < 16:
        return 'london'
    # New York session: 13-21 UTC (overlaps with London)
    elif 13 <= utc_hour < 21:
        return 'newyork'
    else:
        return 'asian'


# Singleton instance
_orchestrator: Optional[StrategyOrchestrator] = None


def get_strategy_orchestrator() -> StrategyOrchestrator:
    """Get the global StrategyOrchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = StrategyOrchestrator()
    return _orchestrator


def get_strategy_weights(
    asset: str,
    timeframe: str,
    regime: str,
    session: str,
    atr_pct: float,
    spread: Optional[float] = None,
) -> List[StrategyWeights]:
    """Convenience function."""
    return get_strategy_orchestrator().get_strategy_weights(
        asset=asset,
        timeframe=timeframe,
        regime=regime,
        session=session,
        atr_pct=atr_pct,
        spread=spread,
    )


def get_best_strategy(
    asset: str,
    timeframe: str,
    regime: str,
    atr_pct: float,
    spread: Optional[float] = None,
) -> Tuple[Optional[str], str]:
    """Convenience function."""
    return get_strategy_orchestrator().get_best_strategy(
        asset=asset,
        timeframe=timeframe,
        regime=regime,
        session=get_current_session(),
        atr_pct=atr_pct,
        spread=spread,
    )
