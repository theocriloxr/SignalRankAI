"""
Advanced Signal Filters
- News/economic event detection
- Overextended move filter
- Choppy market detection
- Correlation clustering
- Fake breakout detection
- Liquidity sweep detection
"""

import os
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import statistics

logger = logging.getLogger(__name__)


class NewsFilter:
    """Filter signals during high-impact news events."""
    
    def __init__(self):
        self.news_events = []
        self.news_buffer_minutes = 30  # Avoid signals 30m before/after news
    
    def is_news_time(
        self,
        symbol: str,
        current_time: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """
        Check if high-impact news is nearby.
        
        Returns: (is_news_time, event_name)
        """
        if not current_time:
            current_time = datetime.utcnow()
        
        # Check for scheduled events
        for event in self.news_events:
            event_time = event.get('time')
            event_impact = event.get('impact', 'low')
            event_currency = event.get('currency', '')
            
            # Only filter high impact news
            if event_impact not in ['high', 'medium']:
                continue
            
            # Check if event affects this symbol
            if event_currency not in symbol:
                continue
            
            # Check if within buffer
            time_diff = abs((event_time - current_time).total_seconds() / 60)
            if time_diff <= self.news_buffer_minutes:
                return True, event.get('name', 'Economic event')
        
        return False, ""
    
    def load_news_calendar(self, events: List[Dict]):
        """
        Load news calendar.
        
        Format: [
            {'time': datetime, 'currency': 'USD', 'impact': 'high', 'name': 'FOMC'},
            ...
        ]
        """
        self.news_events = events


class OverextendedFilter:
    """Detect when price is overextended from moving average."""
    
    def is_overextended(
        self,
        current_price: float,
        ema_20: float,
        ema_50: float,
        atr: float,
        direction: str
    ) -> Tuple[bool, str]:
        """
        Check if price is too far from MA.
        
        Overextended = price > 3*ATR away from EMA50
        """
        # If we don't have reliable values, don't block the signal here.
        if ema_50 <= 0 or atr <= 0 or current_price <= 0:
            return False, ""

        distance = abs(current_price - ema_50)
        # Require both an ATR-based and a small percent-based buffer to avoid false positives
        # when ATR is tiny (common on FX) or EMA is missing.
        threshold = max(3 * atr, 0.02 * ema_50)
        
        if distance > threshold:
            distance_pct = (distance / current_price) * 100
            return True, f"Price {distance_pct:.1f}% from EMA50 (>3 ATR)"
        
        # Also check RSI extremes
        # (Would need RSI passed in, simplified here)
        
        return False, ""


class ChopFilter:
    """Detect choppy/consolidating markets."""
    
    def is_choppy(
        self,
        candles: List[Dict],
        adx: float,
        atr_pct: float,
        lookback: int = 20
    ) -> Tuple[bool, str]:
        """
        Detect consolidation.
        
        Choppy if:
        1. ADX < 20 (weak trend)
        2. ATR% < 3% (low volatility)
        3. Price in tight range
        """
        reasons = []
        
        # Check ADX
        if adx < 20:
            reasons.append(f"Weak trend (ADX {adx:.0f})")
        
        # Check ATR (relax for crypto/FX which are naturally lower volatility)
        if atr_pct < 1.0:
            reasons.append(f"Low volatility (ATR {atr_pct:.1f}%)")
        
        # Check price range (allow tighter ranges for crypto/FX)
        if len(candles) >= lookback:
            recent = candles[-lookback:]
            highs = [c['high'] for c in recent]
            lows = [c['low'] for c in recent]
            
            range_high = max(highs)
            range_low = min(lows)
            range_pct = ((range_high - range_low) / range_low) * 100
            
            if range_pct < 2.0:
                reasons.append(f"Tight range ({range_pct:.1f}%)")
        
        # Only reject if multiple strong reasons; single chop indicator is not enough
        if len(reasons) >= 3:
            return True, " | ".join(reasons)
        
        return False, ""


class CorrelationClusterFilter:
    """Prevent too many correlated signals at once."""
    
    def __init__(self):
        self.active_signals = []
        self.correlation_pairs = {
            'BTCUSDT': ['ETHUSDT', 'BNBUSDT'],
            'ETHUSDT': ['BTCUSDT', 'BNBUSDT'],
            'EURUSD': ['GBPUSD', 'AUDUSD'],
            'GBPUSD': ['EURUSD'],
        }
    
    def can_add_signal(
        self,
        symbol: str,
        direction: str,
        max_correlated: int = 2
    ) -> Tuple[bool, str]:
        """
        Check if adding this signal would create too much correlation.
        
        Max 2 correlated signals in same direction.
        """
        correlated_symbols = self.correlation_pairs.get(symbol, [])
        
        # Count existing correlated signals
        correlated_count = 0
        for sig in self.active_signals:
            if sig['symbol'] in correlated_symbols and sig['direction'] == direction:
                correlated_count += 1
        
        if correlated_count >= max_correlated:
            return False, f"Already have {correlated_count} correlated {direction} signals"
        
        return True, ""
    
    def add_signal(self, symbol: str, direction: str):
        """Record a new signal."""
        self.active_signals.append({
            'symbol': symbol,
            'direction': direction,
            'time': datetime.utcnow()
        })
    
    def remove_signal(self, symbol: str):
        """Remove signal when closed."""
        self.active_signals = [s for s in self.active_signals if s['symbol'] != symbol]


class FakeBreakoutDetector:
    """Detect fake breakouts (head fakes)."""
    
    def is_fake_breakout(
        self,
        candles: List[Dict],
        breakout_level: float,
        direction: str,
        lookback: int = 5
    ) -> Tuple[bool, str]:
        """
        Detect fake breakout.
        
        Fake breakout signs:
        1. Weak volume on breakout candle
        2. Quick rejection (wick)
        3. Failure to hold above/below level
        """
        if len(candles) < lookback:
            return False, ""
        
        breakout_candle = candles[-1]
        previous_candles = candles[-lookback:-1]
        
        # Check volume
        avg_volume = statistics.mean([c.get('volume', 0) for c in previous_candles])
        breakout_volume = breakout_candle.get('volume', 0)
        
        if breakout_volume < avg_volume * 0.8:
            # Low volume breakout - suspicious
            if direction == 'long':
                # Check if rejected below level
                close = breakout_candle['close']
                high = breakout_candle['high']
                
                if high > breakout_level and close < breakout_level:
                    wick_pct = ((high - close) / close) * 100
                    return True, f"Fake breakout: low volume + {wick_pct:.1f}% wick rejection"
            
            elif direction == 'short':
                close = breakout_candle['close']
                low = breakout_candle['low']
                
                if low < breakout_level and close > breakout_level:
                    wick_pct = ((close - low) / close) * 100
                    return True, f"Fake breakout: low volume + {wick_pct:.1f}% wick rejection"
        
        return False, ""


class LiquiditySweepDetector:
    """Detect liquidity sweeps (stop hunts)."""
    
    def detect_sweep(
        self,
        candles: List[Dict],
        direction: str,
        lookback: int = 20
    ) -> Tuple[bool, float]:
        """
        Detect liquidity sweep.
        
        Sweep = brief spike below support (long) or above resistance (short)
        followed by reversal.
        
        Returns: (is_sweep, swept_level)
        """
        if len(candles) < lookback:
            return False, 0.0
        
        recent = candles[-lookback:]
        latest = candles[-1]
        
        if direction == 'long':
            # Look for sweep below support
            lows = [c['low'] for c in recent[:-1]]
            support = min(lows)
            
            # Did latest candle wick below support then close above?
            if latest['low'] < support and latest['close'] > support:
                # Sweep detected
                return True, support
        
        elif direction == 'short':
            # Look for sweep above resistance
            highs = [c['high'] for c in recent[:-1]]
            resistance = max(highs)
            
            # Did latest candle wick above resistance then close below?
            if latest['high'] > resistance and latest['close'] < resistance:
                return True, resistance
        
        return False, 0.0


class LowVolatilityFilter:
    """Filter signals when market ATR is too low."""

    def __init__(self):
        self.atr_multiplier_threshold = 0.5

    def is_low_volatility(self, current_atr: float, average_atr_14d: float) -> Tuple[bool, str]:
        if current_atr <= 0 or average_atr_14d <= 0:
            return False, ""
        ratio = current_atr / average_atr_14d
        if ratio < self.atr_multiplier_threshold:
            return True, f"Market Volatility Too Low (ATR ratio: {ratio:.2%})"
        return False, ""

    def calculate_atr_ratio(self, candles_1h: List[Dict], candles_14d: List[Dict]) -> Tuple[float, float]:
        def _calc_atr(candles: List[Dict]) -> float:
            if not candles or len(candles) < 2:
                return 0.0
            true_ranges = []
            for idx in range(1, len(candles)):
                try:
                    high = float(candles[idx].get("high", 0))
                    low = float(candles[idx].get("low", 0))
                    prev_close = float(candles[idx - 1].get("close", 0))
                    true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
                except Exception:
                    continue
            return statistics.mean(true_ranges) if true_ranges else 0.0

        current_atr = _calc_atr(candles_1h)
        avg_atr = _calc_atr(candles_14d)
        return current_atr, avg_atr


class SessionVolatilityFilter:
    """Filter signals based on session volatility patterns."""
    
    def is_good_session(
        self,
        session: str,
        symbol: str
    ) -> Tuple[bool, str]:
        """
        Check if current session is good for this asset.
        
        Crypto: 24/7 ok
        FX: Prefer overlap sessions
        """
        # Crypto is always ok
        if 'USDT' in symbol or 'USD' in symbol and len(symbol) <= 6:
            return True, ""
        
        # FX preferences
        if session == "ASIA":
            # Good for JPY, AUD, NZD pairs
            if any(curr in symbol for curr in ['JPY', 'AUD', 'NZD']):
                return True, ""
            else:
                return False, "Low liquidity for this pair in Asia session"
        
        elif session == "LONDON_NY_OVERLAP":
            # Best time for FX
            return True, ""
        
        elif session == "LONDON":
            # Good for EUR, GBP pairs
            if any(curr in symbol for curr in ['EUR', 'GBP']):
                return True, ""
        
        elif session == "NY":
            # Good for USD pairs
            if 'USD' in symbol:
                return True, ""
        
        return True, ""


class SmartFilterSuite:
    """Combined filter suite."""
    
    def __init__(self):
        self.news_filter = NewsFilter()
        self.overextended = OverextendedFilter()
        self.chop_filter = ChopFilter()
        self.correlation_filter = CorrelationClusterFilter()
        self.fake_breakout = FakeBreakoutDetector()
        self.liquidity_sweep = LiquiditySweepDetector()
        self.session_filter = SessionVolatilityFilter()
    
    def run_all_filters(
        self,
        signal: Dict,
        market_data: Dict,
        session: str
    ) -> Tuple[bool, List[str]]:
        """
        Run all filters.
        
        Returns: (passed, [rejection_reasons])
        """
        rejections = []
        
        symbol = signal.get('symbol')
        direction = signal.get('direction')
        
        # 1. News filter
        is_news, event = self.news_filter.is_news_time(symbol)
        if is_news:
            rejections.append(f"News event: {event}")
        
        # 2. Overextended filter
        is_over, reason = self.overextended.is_overextended(
            market_data.get('price', 0),
            market_data.get('ema_20', 0),
            market_data.get('ema_50', 0),
            market_data.get('atr', 0),
            direction
        )
        if is_over:
            rejections.append(reason)
        
        # 3. Chop filter
        is_choppy, reason = self.chop_filter.is_choppy(
            market_data.get('candles', []),
            market_data.get('adx', 30),
            market_data.get('atr_pct', 0)
        )
        if is_choppy:
            rejections.append(reason)
        
        # 4. Correlation filter
        can_add, reason = self.correlation_filter.can_add_signal(symbol, direction)
        if not can_add:
            rejections.append(reason)
        
        # 5. Session filter
        good_session, reason = self.session_filter.is_good_session(session, symbol)
        if not good_session:
            rejections.append(reason)
        
        # 6. Fake breakout (if breakout signal)
        if signal.get('trigger') == 'breakout':
            is_fake, reason = self.fake_breakout.is_fake_breakout(
                market_data.get('candles', []),
                signal.get('breakout_level', 0),
                direction
            )
            if is_fake:
                rejections.append(reason)
        
        passed = len(rejections) == 0
        return passed, rejections
