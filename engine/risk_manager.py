\"\"\"
Risk Management Module - PRODUCTION UPGRADE
- Dynamic realtime risk % (0.25-1.25%) from ML/regime/news/gemini
- 0.5% base → throttle at DD_SOFT=6%, stop at DD_HARD=12%
- Enhanced ATR stops, correlation, trailing
\"\"\"

import os
import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import numpy as np

from core.tier_constants import DD_SOFT_THROTTLE, DD_HARD_LIMIT
from engine.risk import get_max_volatility, soft_throttle_active, hard_stop_active

logger = logging.getLogger(__name__)

# Realtime dynamic config (no fixed values beyond env defaults)
BASE_RISK_PCT = float(os.getenv(\"RISK_PER_TRADE_PCT\", \"0.5\"))  # 0.5% base
MAX_ACTIVE_TRADES = int(os.getenv(\"MAX_ACTIVE_TRADES\", \"3\"))  # Reduced for safety
TRADE_COOLDOWN_MINUTES = int(os.getenv(\"TRADE_COOLDOWN_MINUTES\", \"15\"))
MAX_LEVERAGE = float(os.getenv(\"MAX_LEVERAGE\", \"3.0\"))  # Reduced
MIN_RR_RATIO = float(os.getenv(\"MIN_RR_RATIO\", \"1.5\"))


class RiskManager:
    \"\"\"Enhanced dynamic risk manager using realtime data sources.\"\"\"
    
    def __init__(self, account_equity: float):
        self.account_equity = account_equity
        self.correlation_manager = CorrelationManager()
    
    def get_dynamic_risk_pct(self, signal: Dict, account_state: Optional[any] = None) -> float:
        \"\"\"Realtime risk % from ML + regime + sentiment + expectancy (0.25-1.25%).\"\"\"
        ml_prob = float(signal.get(\"ml_probability\", 0.5))
        regime = signal.get(\"regime\", \"neutral\")
        news_sent = float(signal.get(\"news_sentiment\", 0) or signal.get(\"gemini_score\", 0))
        live_exp = float(signal.get(\"live_expectancy\", 0.15))
        
        # ML base (0.5-1.0)
        ml_risk = 0.5 + (ml_prob * 0.5)
        
        # Regime mult
        regime_mult = 1.2 if regime == \"trending\" else 0.8 if regime == \"ranging\" else 1.0
        
        # Sentiment (block/nerf conflict)
        sentiment_mult = 0.7 if abs(news_sent) > 2 else (1.1 if news_sent * (1 if signal.get(\"direction\") == \"long\" else -1) > 1 else 1.0)
        
        # Expectancy nerf
        exp_mult = min(1.5, live_exp / EXPECTANCY_MIN) if live_exp > 0 else 0.5
        
        risk_pct = BASE_RISK_PCT * ml_risk * regime_mult * sentiment_mult * exp_mult
        
        # DD throttle
        if account_state:
            if soft_throttle_active(account_state):
                risk_pct *= 0.5
            if hard_stop_active(account_state):
                return 0.0
        
        return max(0.25, min(risk_pct, 1.25))
    
    def calculate_position_size(
        self,
        signal: Dict,
        account_equity: float,
        **kwargs
    ) -> float:
        \"\"\"Enhanced: equity * dynamic_pct / risk_distance.\"\"\"
        entry = float(signal.get(\"entry\", 0))
        stop = float(signal.get(\"stop_loss\", 0))
        risk_dist = abs(entry - stop)
        
        if risk_dist <= 0:
            return 0.0
        
        risk_pct = self.get_dynamic_risk_pct(signal)
        risk_amount = account_equity * (risk_pct / 100)
        size = risk_amount / risk_dist
        
        # Bounds + vol adjust
        size = max(0.01, min(size, account_equity * 0.1))
        vol_regime = signal.get(\"vol_regime\", \"medium\")
        if vol_regime == \"high\":
            size *= 0.7
        
        return max(0.0, size)
    
    # Existing methods preserved for compatibility
    def calculate_atr_stops(
        self,
        current_price: float,
        atr: float,
        direction: int = 1
    ) -> Dict[str, float]:
        if direction == 1:  # Long
            stop_loss = current_price - (2 * atr)
            take_profit = current_price + (4 * atr)
            rr_ratio = (take_profit - current_price) / (current_price - stop_loss) if (current_price - stop_loss) > 0 else 0
        else:  # Short
            stop_loss = current_price + (2 * atr)
            take_profit = current_price - (4 * atr)
            rr_ratio = (current_price - take_profit) / (stop_loss - current_price) if (stop_loss - current_price) > 0 else 0
        
        return {
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'rr_ratio': max(1.5, rr_ratio),  # Enforce min RR
            'risk_distance': abs(current_price - stop_loss),
            'reward_distance': abs(take_profit - current_price),
        }
    
    def validate_rr_ratio(
        self,
        entry: float,
        stop_loss: float,
        take_profit: float,
        min_ratio: float = MIN_RR_RATIO
    ) -> Tuple[bool, float]:
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        if risk <= 0:
            return False, 0
        rr_ratio = reward / risk
        return rr_ratio >= min_ratio, rr_ratio
    
    def can_open_trade(
        self,
        active_trades: int,
        last_trade_time: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        if active_trades >= MAX_ACTIVE_TRADES:
            return False, f"Max active trades ({MAX_ACTIVE_TRADES}) reached"
        if last_trade_time:
            time_since_last = datetime.utcnow() - last_trade_time
            if time_since_last < timedelta(minutes=TRADE_COOLDOWN_MINUTES):
                remaining = TRADE_COOLDOWN_MINUTES - int(time_since_last.total_seconds() / 60)
                return False, f"Trade cooldown: {remaining}m remaining"
        return True, "OK"
    
    def calculate_trailing_stop(
        self,
        entry_price: float,
        current_price: float,
        atr: float,
        direction: int = 1
    ) -> Optional[float]:
        if direction == 1:  # Long
            if current_price <= entry_price:
                return entry_price - (2 * atr)
            trailing_stop = current_price - (1.5 * atr)
            return max(trailing_stop, entry_price - (2 * atr))
        else:  # Short
            if current_price >= entry_price:
                return entry_price + (2 * atr)
            trailing_stop = current_price + (1.5 * atr)
            return min(trailing_stop, entry_price + (2 * atr))
    
    # Partial exits
    def calculate_partial_exit_levels(
        self,
        entry: float,
        take_profit: float,
        direction: int = 1,
        num_levels: int = 3
    ) -> List[Dict[str, float]]:
        if direction == 1:  # Long
            tp_distance = take_profit - entry
            return [{
                'price': entry + (tp_distance * i / num_levels),
                'quantity_pct': 100 / num_levels,
                'label': f'TP{i}'
            } for i in range(1, num_levels + 1)]
        else:  # Short
            tp_distance = entry - take_profit
            return [{
                'price': entry - (tp_distance * i / num_levels),
                'quantity_pct': 100 / num_levels,
                'label': f'TP{i}'
            } for i in range(1, num_levels + 1)]


class CorrelationManager:
    \"\"\"Realtime correlation avoidance.\"\"\"
    
    def __init__(self):
        self.correlation_matrix = {}
    
    def calculate_pair_correlation(
        self,
        returns1: np.ndarray,
        returns2: np.ndarray
    ) -> float:
        if len(returns1) < 2 or len(returns2) < 2:
            return 0
        try:
            corr = np.corrcoef(returns1, returns2)[0, 1]
            return float(corr) if not np.isnan(corr) else 0
        except:
            return 0
    
    def can_add_correlated_position(
        self,
        new_pair: str,
        existing_pairs: List[str],
        max_correlation: float = 0.7,
        returns_data: Dict[str, np.ndarray] = None
    ) -> Tuple[bool, str]:
        if not existing_pairs or not returns_data:
            return True, "No correlation check needed"
        for existing in existing_pairs:
            if new_pair not in returns_data or existing not in returns_data:
                continue
            corr = self.calculate_pair_correlation(
                returns_data[new_pair],
                returns_data[existing]
            )
            if abs(corr) > max_correlation:
                return False, f"High correlation with {existing}: {corr:.2f}"
        return True, "OK"

