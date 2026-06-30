"""
Signal Context Module
- Entry zones (not single prices)
- Candle close confirmation
- Signal expiration
- Session detection
- Signal invalidation rules
"""

import os
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SignalContext:
    """Manages signal context: entry zones, validity, expiration."""
    
    def __init__(self):
        self.active_signals = {}
        self.signal_history = []
    
    def calculate_entry_zone(
        self,
        entry_price: float,
        atr: float,
        direction: str,
        tolerance_pct: float = 1.0
    ) -> Dict:
        """
        Calculate entry zone (range) instead of single price.
        
        Entry zone = entry_price ± (tolerance% or 0.5*ATR, whichever smaller)
        """
        # Use smaller of: 1% or 0.5*ATR
        tolerance_by_pct = entry_price * (tolerance_pct / 100)
        tolerance_by_atr = atr * 0.5
        tolerance = min(tolerance_by_pct, tolerance_by_atr)
        
        zone_low = entry_price - tolerance
        zone_high = entry_price + tolerance
        
        return {
            'entry_price': entry_price,
            'zone_low': zone_low,
            'zone_high': zone_high,
            'zone_width_pct': (tolerance / entry_price) * 100,
            'status': self._get_entry_status(entry_price, zone_low, zone_high, entry_price)
        }
    
    def _get_entry_status(
        self,
        current_price: float,
        zone_low: float,
        zone_high: float,
        ideal_entry: float
    ) -> str:
        """
        Determine entry status.
        
        Returns: BUY, SELL, WAIT
        """
        if zone_low <= current_price <= zone_high:
            return "BUY" if current_price <= ideal_entry else "SELL"
        elif current_price < zone_low:
            return "WAIT (below zone)"
        else:
            return "WAIT (above zone)"
    
    def wait_for_candle_close(
        self,
        candles: List[Dict],
        timeframe: str
    ) -> bool:
        """
        Check if current candle has closed.
        
        No mid-candle signals - only alert after close.
        """
        if not candles:
            return False
        
        latest_candle = candles[-1]
        
        # Check if candle is final
        is_final = latest_candle.get('is_final', False)
        
        if is_final:
            return True
        
        # Fallback: check time
        close_time_ms = latest_candle.get('close_time_ms', 0)
        current_time_ms = int(datetime.utcnow().timestamp() * 1000)
        
        # If close time has passed, candle is closed
        return current_time_ms >= close_time_ms
    
    def calculate_signal_expiration(
        self,
        timeframe: str,
        candles_validity: int = 2
    ) -> datetime:
        """
        Calculate when signal expires.
        
        Default: valid for next 2 candles of the timeframe
        """
        tf_minutes = {
            '1m': 1, '5m': 5, '15m': 15, '30m': 30,
            '1h': 60, '4h': 240, '1d': 1440
        }
        
        minutes = tf_minutes.get(timeframe, 60)
        validity_minutes = minutes * candles_validity
        
        return datetime.utcnow() + timedelta(minutes=validity_minutes)
    
    def check_signal_invalidation(
        self,
        signal: Dict,
        current_price: float,
        indicators: Dict
    ) -> Tuple[bool, str]:
        """
        Check if signal should be invalidated.
        
        Invalidation rules:
        1. Price crosses invalidation level (kill zone)
        2. Trend reverses (HTF bias flips)
        3. Signal expired
        """
        # Rule 1: Kill zone
        kill_zone = signal.get('invalid_if_price')
        if kill_zone:
            direction = signal.get('direction', 'long')
            if direction == 'long' and current_price < kill_zone:
                return True, f"Price crossed kill zone: {current_price} < {kill_zone}"
            elif direction == 'short' and current_price > kill_zone:
                return True, f"Price crossed kill zone: {current_price} > {kill_zone}"
        
        # Rule 2: Expiration
        expires_at = signal.get('expires_at')
        if expires_at:
            if datetime.utcnow() > expires_at:
                return True, "Signal expired"
        
        # Rule 3: HTF bias flip
        htf_bias = indicators.get('htf_bias', {})
        original_bias = signal.get('htf_bias_at_creation')
        if original_bias and htf_bias.get('bias') != original_bias:
            return True, f"HTF bias flipped: {original_bias} -> {htf_bias.get('bias')}"
        
        return False, "Signal still valid"
    
    def detect_trading_session(self) -> str:
        """
        Detect current trading session.
        
        Returns: ASIA, LONDON, NY, or OVERLAP
        """
        utc_hour = datetime.utcnow().hour
        
        # Session times (UTC)
        # Asia: 00:00-09:00
        # London: 08:00-17:00
        # NY: 13:00-22:00
        
        if 0 <= utc_hour < 8:
            return "ASIA"
        elif 8 <= utc_hour < 13:
            return "LONDON"
        elif 13 <= utc_hour < 17:
            return "LONDON_NY_OVERLAP"
        elif 17 <= utc_hour < 22:
            return "NY"
        else:
            return "ASIA_OPENING"
    
    def should_send_no_trade_alert(
        self,
        market_conditions: Dict,
        last_alert_time: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """
        Determine if NO TRADE alert should be sent.
        
        Criteria:
        - Low volume
        - High volatility
        - Choppy market
        - News event nearby
        - Only send once per 4 hours
        """
        reasons = []
        
        # Check volume
        volume_ratio = market_conditions.get('volume_ratio', 1.0)
        if volume_ratio < 0.5:
            reasons.append("Low volume (<50% avg)")
        
        # Check volatility
        atr_pct = market_conditions.get('atr_percent', 0)
        if atr_pct > 15.0:
            reasons.append("Extreme volatility (>15%)")
        
        # Check regime
        regime = market_conditions.get('regime', 'unknown')
        if regime == 'ranging' and market_conditions.get('adx', 30) < 15:
            reasons.append("Choppy ranging market (ADX <15)")
        
        # Check spread
        spread_pct = market_conditions.get('spread_pct', 0)
        if spread_pct > 2.0:
            reasons.append("Wide spread (>2%)")
        
        # Only alert if we have reasons
        if not reasons:
            return False, ""
        
        # Rate limit: only send once per 4 hours
        if last_alert_time:
            now = datetime.utcnow()
            try:
                if getattr(last_alert_time, "tzinfo", None) is not None:
                    now = datetime.now(last_alert_time.tzinfo)
            except Exception:
                now = datetime.utcnow()
            time_since_last = now - last_alert_time
            if time_since_last < timedelta(hours=4):
                return False, "Too soon since last NO TRADE alert"
        
        reason_text = " | ".join(reasons)
        return True, reason_text
    
    def calculate_expected_holding_time(
        self,
        timeframe: str,
        rr_ratio: float
    ) -> str:
        """
        Estimate expected holding time based on TF and R:R.
        
        Higher R:R = longer hold
        Higher TF = longer hold
        """
        tf_base_hours = {
            '5m': 0.5, '15m': 1, '1h': 4, '4h': 12, '1d': 48
        }
        
        base_hours = tf_base_hours.get(timeframe, 4)
        
        # Adjust for R:R
        adjusted_hours = base_hours * (rr_ratio / 2.0)
        
        if adjusted_hours < 1:
            return f"{int(adjusted_hours * 60)}m"
        elif adjusted_hours < 24:
            return f"{int(adjusted_hours)}h"
        else:
            return f"{int(adjusted_hours / 24)}d"


class SignalCooldownManager:
    """Manages cooldown between signals."""
    
    def __init__(self):
        self.last_signal_times = {}
    
    def can_send_signal(
        self,
        symbol: str,
        timeframe: str,
        cooldown_minutes: int = 60
    ) -> Tuple[bool, str]:
        """
        Check if enough time has passed since last signal.
        
        Prevents spam of same pair/TF.
        """
        key = f"{symbol}_{timeframe}"
        last_time = self.last_signal_times.get(key)
        
        if not last_time:
            return True, "No previous signal"
        
        time_since = datetime.utcnow() - last_time
        cooldown = timedelta(minutes=cooldown_minutes)
        
        if time_since < cooldown:
            remaining = int((cooldown - time_since).total_seconds() / 60)
            return False, f"Cooldown: {remaining}m remaining"
        
        return True, "Cooldown passed"
    
    def record_signal(self, symbol: str, timeframe: str):
        """Record that a signal was sent."""
        key = f"{symbol}_{timeframe}"
        self.last_signal_times[key] = datetime.utcnow()


class OneBiasPerTimeframe:
    """Ensures only one directional bias per pair/timeframe."""
    
    def __init__(self):
        self.active_biases = {}
    
    def can_add_signal(
        self,
        symbol: str,
        timeframe: str,
        direction: str
    ) -> Tuple[bool, str]:
        """
        Check if we can add a signal in this direction.
        
        Only one direction per TF at a time.
        """
        key = f"{symbol}_{timeframe}"
        existing = self.active_biases.get(key)
        
        if not existing:
            return True, "No existing bias"
        
        if existing == direction:
            return False, f"Already have {direction} signal for {symbol} {timeframe}"
        else:
            return False, f"Conflicting bias: existing {existing}, new {direction}"
    
    def set_bias(self, symbol: str, timeframe: str, direction: str):
        """Set the active bias."""
        key = f"{symbol}_{timeframe}"
        self.active_biases[key] = direction
    
    def clear_bias(self, symbol: str, timeframe: str):
        """Clear bias when signal closes."""
        key = f"{symbol}_{timeframe}"
        if key in self.active_biases:
            del self.active_biases[key]
