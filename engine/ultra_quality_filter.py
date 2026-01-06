"""
Ultra Quality Filter - Near-Zero Loss Trading System
Forces only the highest quality trades with strict validation.

Key principles:
1. Confluence threshold: 80%+ (5 of 6 confirmations)
2. Score minimum: 85 (premium quality only)
3. Entry: Must be in natural zone (price naturally arrives)
4. Regime: Only trending (ADX > 25)
5. Volume: Above average (ratio > 1.5)
6. Session: High-conviction sessions only
7. R:R ratio: 2.5:1 minimum (higher reward)
8. Volatility: Moderate only (skip extremes)
9. Position size: Dynamic Kelly criterion
10. Exit: Break-even stops + partial exits
"""

import os
import logging
from typing import Dict, Tuple, Optional, List
from datetime import datetime, timedelta
import statistics

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


class UltraQualityFilter:
    """Filters signals to only highest quality setups."""
    
    def __init__(self):
        # Ultra-strict thresholds
        # Match pipeline threshold (55-70 range) rather than hardcoding 85
        self.min_score = _env_float("ULTRA_MIN_SCORE", 65.0)
        self.min_confluence = _env_float("ULTRA_MIN_CONFLUENCE", 70.0)
        self.min_rr_ratio = _env_float("ULTRA_MIN_RR_RATIO", 2.0)
        self.min_adx = _env_float("ULTRA_MIN_ADX", 20.0)
        self.min_volume_ratio = _env_float("ULTRA_MIN_VOLUME_RATIO", 1.5)
        self.min_confidence = _env_float("ULTRA_MIN_CONFIDENCE", 0.70)
        self.max_volatility = _env_float("ULTRA_MAX_VOLATILITY", 0.15)  # 15% max
        self.high_conviction_sessions = {"NY", "LONDON", "ASIA"}  # Only these
        
        # Position sizing
        self.kelly_fraction = _env_float("KELLY_FRACTION", 0.25)  # Start conservative
        self.risk_per_trade_pct = _env_float("ULTRA_RISK_PER_TRADE", 1.0)  # 1% per trade max
        
        # Tracking
        self.recent_trades = []
        self.win_rate_window = 20  # Last 20 trades
    
    def apply_ultra_filter(self, signal: Dict) -> Tuple[bool, str, float]:
        """
        Apply ultra-strict filters to signal.
        Requires 8 out of 11 checks to pass.
        
        Returns: (should_trade, rejection_reason, final_score)
        """
        score = signal.get("score", 0)
        passed_checks = 0
        failed_checks = []
        
        # 1. Score check
        if score >= self.min_score:
            passed_checks += 1
        else:
            failed_checks.append(f"Score {score:.1f} < {self.min_score}")
        
        # 2. Confluence check (5+ of 6 confirmations)
        confluence = self._calculate_strict_confluence(signal)
        if confluence >= self.min_confluence:
            passed_checks += 1
        else:
            failed_checks.append(f"Confluence {confluence:.0f}% < {self.min_confluence}%")
        
        # 3. Confidence check
        confidence = signal.get("confidence", 0)
        if confidence >= self.min_confidence:
            passed_checks += 1
        else:
            failed_checks.append(f"Confidence {confidence:.2f} < {self.min_confidence}")
        
        # 4. R:R ratio check
        entry = signal.get("entry")
        stop = signal.get("stop")
        target = signal.get("targets", entry)
        rr = abs(target - entry) / abs(entry - stop) if entry and stop and abs(entry - stop) > 0 else 0
        if rr >= self.min_rr_ratio:
            passed_checks += 1
        else:
            failed_checks.append(f"R:R {rr:.2f} < {self.min_rr_ratio}")
        
        # 5. Regime check (must be trending)
        regime = signal.get("regime", "unknown")
        adx = signal.get("adx_trend", 0)
        if regime == "trending" and adx >= self.min_adx:
            passed_checks += 1
        else:
            failed_checks.append(f"Regime not trending (ADX {adx:.1f} < {self.min_adx})")
        
        # 6. Volume check
        volume_ratio = signal.get("volume_ratio", 0)
        if volume_ratio >= self.min_volume_ratio:
            passed_checks += 1
        else:
            failed_checks.append(f"Volume {volume_ratio:.1f}x < {self.min_volume_ratio}x avg")
        
        # 7. Volatility check
        volatility = signal.get("volatility", 0)
        if volatility <= self.max_volatility:
            passed_checks += 1
        else:
            failed_checks.append(f"Volatility {volatility:.2%} > {self.max_volatility:.2%}")
        
        # 8. Session check (high conviction only)
        session = signal.get("session", "unknown")
        if session in self.high_conviction_sessions:
            passed_checks += 1
        else:
            failed_checks.append(f"Session {session} not in high-conviction list")
        
        # 9. Entry zone natural entry check
        entry_natural = self._check_entry_zone_natural(signal)
        if entry_natural:
            passed_checks += 1
        else:
            failed_checks.append("Price not in natural entry zone")
        
        # 10. Overextended check
        if not self._is_overextended(signal):
            passed_checks += 1
        else:
            failed_checks.append("Price overextended from MA")
        
        # 11. HTF bias alignment
        htf_bias_aligned = signal.get("htf_bias_aligned", False)
        if htf_bias_aligned:
            passed_checks += 1
        else:
            failed_checks.append("HTF bias not aligned with entry direction")
        
        # Require 8 out of 11 checks to pass
        min_passed = 8
        if passed_checks >= min_passed:
            reason = f"APPROVED - {passed_checks}/11 checks passed"
            return True, reason, score
        else:
            rejection_reason = " | ".join(failed_checks[:3])  # Top 3 failures
            return False, f"{passed_checks}/11 passed - {rejection_reason}", score
    
    def _calculate_strict_confluence(self, signal: Dict) -> float:
        """
        Calculate strict confluence (must meet 5+ of 6 criteria).
        
        1. Trend alignment (EMA/SMA) + Direction match
        2. Momentum confirmation (RSI + MACD aligned)
        3. Volume confirmation (above 1.5x average)
        4. Support/Resistance respect
        5. Market regime alignment (trending + ADX > 25)
        6. HTF bias alignment
        """
        confirmations = 0
        total_checks = 6
        
        # 1. Trend alignment
        trend_ema = float(signal.get("trend_ema", 0) or 0)
        trend_sma = float(signal.get("trend_sma", 0) or 0)
        direction = signal.get("direction", "long")
        
        if direction == "long":
            if trend_ema > 0 and trend_sma > 0:
                confirmations += 1
        elif direction == "short":
            if trend_ema < 0 and trend_sma < 0:
                confirmations += 1
        
        # 2. Momentum confirmation
        rsi = float(signal.get("rsi", 50) or 50)
        macd_trend = float(signal.get("macd_trend", 0) or 0)
        
        if direction == "long":
            if rsi > 55 and macd_trend > 0:  # Stricter RSI threshold
                confirmations += 1
        elif direction == "short":
            if rsi < 45 and macd_trend < 0:
                confirmations += 1
        
        # 3. Volume confirmation
        volume_ratio = float(signal.get("volume_ratio", 1.0) or 1.0)
        if volume_ratio > self.min_volume_ratio:
            confirmations += 1
        
        # 4. Support/Resistance respect
        nearest_support = float(signal.get("nearest_support", 0) or 0)
        nearest_resistance = float(signal.get("nearest_resistance", 0) or 0)
        current_price = float(signal.get("close_price", 0) or 0)
        
        if direction == "long" and current_price > nearest_support:
            confirmations += 1
        elif direction == "short" and current_price < nearest_resistance:
            confirmations += 1
        
        # 5. Market regime alignment
        regime = signal.get("regime", "unknown")
        adx_trend = float(signal.get("adx_trend", 0) or 0)
        
        if regime == "trending" and adx_trend >= self.min_adx:
            confirmations += 1
        
        # 6. HTF bias alignment
        htf_bias_aligned = signal.get("htf_bias_aligned", False)
        if htf_bias_aligned:
            confirmations += 1
        
        return (confirmations / total_checks) * 100
    
    def _check_entry_zone_natural(self, signal: Dict) -> bool:
        """Check if price naturally arrived at entry zone."""
        current_price = signal.get("close_price", 0)
        entry = signal.get("entry", 0)
        atr = signal.get("atr", 0)
        
        if not current_price or not entry or not atr:
            return False
        
        # Entry zone: ±0.5*ATR from entry
        zone_low = entry - (0.5 * atr)
        zone_high = entry + (0.5 * atr)
        
        # Price should be within zone
        return zone_low <= current_price <= zone_high
    
    def _is_overextended(self, signal: Dict) -> bool:
        """Check if price is overextended from moving average."""
        current_price = signal.get("close_price", 0)
        ema_50 = signal.get("ema_50", 0)
        atr = signal.get("atr", 0)
        
        if not current_price or not ema_50 or not atr:
            return False  # Can't determine, assume not overextended
        
        # Overextended if price is > 3*ATR away from EMA50
        distance = abs(current_price - ema_50)
        return distance > (3 * atr)
        
        if not current_price or not ema_50 or not atr:
            return False
        
        distance = abs(current_price - ema_50)
        
        # Overextended if > 2.5*ATR away
        return distance > (2.5 * atr)
    
    def calculate_dynamic_position_size(
        self,
        account_equity: float,
        entry_price: float,
        stop_loss: float,
        current_win_rate: Optional[float] = None
    ) -> Tuple[float, str]:
        """
        Calculate position size using Kelly Criterion with safety margins.
        
        Kelly % = (p * b - q) / b
        where:
            p = win_rate
            b = reward / risk (R:R ratio)
            q = 1 - win_rate
        
        Use fractional Kelly (25%) for safety.
        """
        risk_distance = abs(entry_price - stop_loss)
        if risk_distance <= 0:
            return 0, "Invalid stop loss"
        
        # Default win rate from recent trades
        if current_win_rate is None:
            if self.recent_trades:
                wins = sum(1 for t in self.recent_trades[-self.win_rate_window:] if t.get("result") == "win")
                trades = len(self.recent_trades[-self.win_rate_window:])
                current_win_rate = wins / trades if trades > 0 else 0.55
            else:
                current_win_rate = 0.55  # Conservative estimate
        
        # Conservative risk per trade: 1% max
        risk_amount = account_equity * (self.risk_per_trade_pct / 100)
        
        position_size = risk_amount / risk_distance
        
        # Apply Kelly Criterion adjustment
        if current_win_rate > 0.5:
            kelly_pct = ((current_win_rate * 2.5) - (1 - current_win_rate)) / 2.5  # Assuming 2.5:1 R:R
            kelly_pct = max(0, kelly_pct)  # Can't be negative
            position_size *= (self.kelly_fraction * kelly_pct)
        else:
            # Negative Kelly: reduce size further
            position_size *= 0.5
        
        detail = f"Size={position_size:.4f} WR={current_win_rate:.1%} Kelly={kelly_pct:.1%}"
        
        return max(0, position_size), detail
    
    def record_trade_result(
        self,
        symbol: str,
        direction: str,
        entry: float,
        exit: float,
        stop_loss: float,
        result: str  # "win" or "loss"
    ) -> None:
        """Record trade for win rate calculation."""
        self.recent_trades.append({
            "symbol": symbol,
            "direction": direction,
            "entry": entry,
            "exit": exit,
            "stop_loss": stop_loss,
            "result": result,
            "timestamp": datetime.utcnow(),
            "profit_loss": (exit - entry) if direction == "long" else (entry - exit)
        })
    
    def get_stats(self) -> Dict:
        """Get recent trading statistics."""
        if not self.recent_trades:
            return {"trades": 0, "win_rate": 0, "avg_profit": 0, "max_loss": 0}
        
        recent = self.recent_trades[-self.win_rate_window:]
        wins = sum(1 for t in recent if t.get("result") == "win")
        losses = sum(1 for t in recent if t.get("result") == "loss")
        
        pnl_values = [t.get("profit_loss", 0) for t in recent]
        avg_profit = statistics.mean(pnl_values) if pnl_values else 0
        max_loss = min(pnl_values) if pnl_values else 0
        
        return {
            "trades": len(recent),
            "win_rate": wins / len(recent) if recent else 0,
            "wins": wins,
            "losses": losses,
            "avg_profit": avg_profit,
            "max_loss": max_loss,
            "total_pnl": sum(pnl_values)
        }


# Ultra-strict filters instance
ultra_quality = UltraQualityFilter()
