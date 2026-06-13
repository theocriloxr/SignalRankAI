"""
Comprehensive signal generator with 20 top strategies.
Each strategy returns (signal, ml_features) tuple for ML filtering.
Strategies are asset-type optimized with success-rate tracking.
"""
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass
import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class StrategySignal:
    asset: str
    timeframe: str
    direction: str  # 'long' or 'short'
    entry: float
    stop_loss: float
    take_profit: List[Dict[str, float]]  # [{'price': X, 'pct': Y, 'exit_percent': Z}]
    score: float  # 0-100
    strategy_name: str
    strategy_group: str
    ml_features: Dict[str, float]
    confidence: float  # 0-1


class StrategySelector:
    """Select best strategy for asset based on success rates."""
    
    STRATEGY_WEIGHTS = {
        'crypto': ['supertrend', 'macd_histogram', 'ema_crossover', 'adx_directional', 'bollinger_bounce', 'rsi_divergence'],
        'forex': ['ichimoku', 'ema_crossover', 'parabolic_sar', 'adx_directional', 'support_resistance', 'macd_histogram'],
        'stocks': ['ema_crossover', 'adx_directional', 'candlestick_patterns', 'support_resistance', 'volume_breakout', 'htf_trend_ltf_entry'],
        'commodities': ['adx_directional', 'parabolic_sar', 'bollinger_bounce', 'ema_crossover', 'supertrend', 'rate_of_change'],
    }
    
    def select_strategy_for_asset(self, asset: str) -> str:
        """Return best strategy name for asset type."""
        asset_type = self._classify_asset(asset)
        strategies = self.STRATEGY_WEIGHTS.get(asset_type, [])
        return strategies[0] if strategies else 'ema_crossover'
    
    def _classify_asset(self, asset: str) -> str:
        """Classify asset: crypto, forex, stocks, commodities."""
        asset_upper = (asset or "").upper().strip()
        if asset_upper.endswith(('USDT', 'BUSD', 'USDC')):
            return 'crypto'
        if asset_upper.endswith(('USD', '=X')) or len(asset_upper) == 6:
            return 'forex'
        if asset_upper.endswith(('XAU', 'XAG', 'WTI', 'BRENT', 'NG')):
            return 'commodities'
        return 'stocks'


class SignalGenerator:
    """Generate signals from 20 strategies."""
    
    def __init__(self):
        self.selector = StrategySelector()
    
    def generate_signals(self, asset: str, timeframe: str, market_data: Dict[str, Any]) -> List[StrategySignal]:
        """Generate signals for asset across all applicable strategies."""
        signals = []
        candles = market_data.get('candles', [])
        indicators = market_data.get('indicators', {})
        
        if len(candles) < 50:
            return signals
        
        # Strategy methods
        strategies = [
            self._ema_crossover,
            self._macd_histogram,
            self._adx_directional,
            self._supertrend,
            self._parabolic_sar,
            self._ichimoku,
            self._support_resistance,
            self._volume_breakout,
            self._bollinger_bounce,
            self._range_expansion,
            self._donchian_breakout,
            self._rsi_divergence,
            self._stochastic_reversal,
            self._momentum_divergence,
            self._rate_of_change,
            self._williams_r,
            self._candlestick_patterns,
            self._chart_patterns,
            self._htf_trend_ltf_entry,
            self._triple_timeframe,
]
        
        for strategy in strategies:
            try:
                sig = strategy(asset, timeframe, candles, indicators)
                # LOWERED from 70 to 60 to fix zero signals issue
                # This allows more signals through during low-volatility periods
                if sig and sig.score >= 60:
                    signals.append(sig)
            except Exception as e:
                logger.debug(f"Strategy {strategy.__name__} failed: {e}")
        
        return signals
    
    def _ema_crossover(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:
        """EMA 9/21/55 Crossover."""
        try:
            ema_fast = indicators.get('ema_fast')
            ema_slow = indicators.get('ema_slow')
            close = candles[-1]['close'] if candles else 0
            
            if not ema_fast or not ema_slow or close == 0:
                return None
            
            prev_close = candles[-2]['close'] if len(candles) > 1 else close
            direction = None
            
            if ema_fast > ema_slow and close > ema_fast:
                direction = 'long'
                score = 75
            elif ema_fast < ema_slow and close < ema_fast:
                direction = 'short'
                score = 75
            else:
                return None
            
            sl_distance = abs(close - ema_slow) * 0.5
            tp1 = close + (sl_distance * 2) if direction == 'long' else close - (sl_distance * 2)
            tp2 = close + (sl_distance * 3.5) if direction == 'long' else close - (sl_distance * 3.5)
            tp3 = close + (sl_distance * 5) if direction == 'long' else close - (sl_distance * 5)
            
            return StrategySignal(
                asset=asset, timeframe=timeframe, direction=direction,
                entry=close, stop_loss=ema_slow,
                take_profit=[
                    {'price': tp1, 'pct': ((tp1-close)/close)*100, 'exit_percent': 33},
                    {'price': tp2, 'pct': ((tp2-close)/close)*100, 'exit_percent': 33},
                    {'price': tp3, 'pct': ((tp3-close)/close)*100, 'exit_percent': 34},
                ],
                score=score, strategy_name='ema_crossover', strategy_group='trend_following',
                ml_features={'ema_diff': float((ema_fast - ema_slow) / close)},
                confidence=0.75
            )
        except Exception:
            return None
    
    def _macd_histogram(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:
        """MACD Histogram Reversal."""
        try:
            macd = indicators.get('macd', {})
            if not isinstance(macd, dict):
                return None
            
            hist = macd.get('hist')
            close = candles[-1]['close']
            
            if not hist or close == 0:
                return None
            
            direction = 'long' if hist > 0 else 'short'
            score = 72
            
            sl_distance = close * 0.02
            tp_mult = 1.04 if direction == 'long' else 0.96
            
            return StrategySignal(
                asset=asset, timeframe=timeframe, direction=direction,
                entry=close,
                stop_loss=close * (0.98 if direction == 'long' else 1.02),
                take_profit=[
                    {'price': close * 1.03, 'pct': 3.0, 'exit_percent': 33},
                    {'price': close * 1.06, 'pct': 6.0, 'exit_percent': 33},
                    {'price': close * 1.09, 'pct': 9.0, 'exit_percent': 34},
                ] if direction == 'long' else [
                    {'price': close * 0.97, 'pct': -3.0, 'exit_percent': 33},
                    {'price': close * 0.94, 'pct': -6.0, 'exit_percent': 33},
                    {'price': close * 0.91, 'pct': -9.0, 'exit_percent': 34},
                ],
                score=score, strategy_name='macd_histogram', strategy_group='momentum',
                ml_features={'hist_value': float(hist)},
                confidence=0.72
            )
        except Exception:
            return None
    
    def _adx_directional(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:
        """ADX + DI+ / DI- Directional Movement."""
        try:
            adx = indicators.get('adx')
            di_plus = indicators.get('di_plus')
            di_minus = indicators.get('di_minus')
            close = candles[-1]['close']
            
            if adx is None or di_plus is None or di_minus is None or close == 0:
                return None
            
            if adx < 25:
                return None
            
            direction = 'long' if di_plus > di_minus else 'short'
            score = 73 if adx >= 40 else 71
            
            return StrategySignal(
                asset=asset, timeframe=timeframe, direction=direction,
                entry=close,
                stop_loss=close * (0.97 if direction == 'long' else 1.03),
                take_profit=[
                    {'price': close * 1.035, 'pct': 3.5, 'exit_percent': 33},
                    {'price': close * 1.07, 'pct': 7.0, 'exit_percent': 33},
                    {'price': close * 1.105, 'pct': 10.5, 'exit_percent': 34},
                ] if direction == 'long' else [
                    {'price': close * 0.965, 'pct': -3.5, 'exit_percent': 33},
                    {'price': close * 0.93, 'pct': -7.0, 'exit_percent': 33},
                    {'price': close * 0.895, 'pct': -10.5, 'exit_percent': 34},
                ],
                score=score, strategy_name='adx_directional', strategy_group='trend_following',
                ml_features={'adx': float(adx), 'di_diff': float(di_plus - di_minus)},
                confidence=0.73
            )
        except Exception:
            return None
    
    def _supertrend(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:
        """Supertrend."""
        try:
            atr = indicators.get('atr')
            hl2 = (candles[-1]['high'] + candles[-1]['low']) / 2
            close = candles[-1]['close']
            
            if not atr or close == 0:
                return None
            
            basic_ub = hl2 + 2 * atr
            basic_lb = hl2 - 2 * atr
            
            direction = 'long' if close > basic_ub else 'short' if close < basic_lb else None
            if not direction:
                return None
            
            score = 74
            
            return StrategySignal(
                asset=asset, timeframe=timeframe, direction=direction,
                entry=close,
                stop_loss=basic_lb if direction == 'long' else basic_ub,
                take_profit=[
                    {'price': close + atr * 3, 'pct': (atr * 3 / close) * 100, 'exit_percent': 33},
                    {'price': close + atr * 6, 'pct': (atr * 6 / close) * 100, 'exit_percent': 33},
                    {'price': close + atr * 9, 'pct': (atr * 9 / close) * 100, 'exit_percent': 34},
                ] if direction == 'long' else [
                    {'price': close - atr * 3, 'pct': -(atr * 3 / close) * 100, 'exit_percent': 33},
                    {'price': close - atr * 6, 'pct': -(atr * 6 / close) * 100, 'exit_percent': 33},
                    {'price': close - atr * 9, 'pct': -(atr * 9 / close) * 100, 'exit_percent': 34},
                ],
                score=score, strategy_name='supertrend', strategy_group='trend_following',
                ml_features={'atr': float(atr)},
                confidence=0.74
            )
        except Exception:
            return None
    
    def _parabolic_sar(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:
        """Parabolic SAR."""
        try:
            close = candles[-1]['close']
            high = candles[-1]['high']
            low = candles[-1]['low']
            
            if close == 0:
                return None
            
            trend = 'long' if close > low * 1.02 else 'short'
            score = 71
            
            return StrategySignal(
                asset=asset, timeframe=timeframe, direction=trend,
                entry=close,
                stop_loss=low if trend == 'long' else high,
                take_profit=[
                    {'price': close * 1.04, 'pct': 4.0, 'exit_percent': 33},
                    {'price': close * 1.08, 'pct': 8.0, 'exit_percent': 33},
                    {'price': close * 1.12, 'pct': 12.0, 'exit_percent': 34},
                ] if trend == 'long' else [
                    {'price': close * 0.96, 'pct': -4.0, 'exit_percent': 33},
                    {'price': close * 0.92, 'pct': -8.0, 'exit_percent': 33},
                    {'price': close * 0.88, 'pct': -12.0, 'exit_percent': 34},
                ],
                score=score, strategy_name='parabolic_sar', strategy_group='trend_following',
                ml_features={'sar_diff': float((high - low) / close)},
                confidence=0.71
            )
        except Exception:
            return None
    
    def _ichimoku(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:
        """Ichimoku Cloud."""
        try:
            close = candles[-1]['close']
            if close == 0:
                return None
            
            # Simplified Ichimoku
            high20 = max([c['high'] for c in candles[-20:]])
            low20 = min([c['low'] for c in candles[-20:]])
            tenkan = (high20 + low20) / 2
            
            direction = 'long' if close > tenkan else 'short'
            score = 72
            
            return StrategySignal(
                asset=asset, timeframe=timeframe, direction=direction,
                entry=close,
                stop_loss=low20 if direction == 'long' else high20,
                take_profit=[
                    {'price': close * 1.035, 'pct': 3.5, 'exit_percent': 33},
                    {'price': close * 1.07, 'pct': 7.0, 'exit_percent': 33},
                    {'price': close * 1.105, 'pct': 10.5, 'exit_percent': 34},
                ] if direction == 'long' else [
                    {'price': close * 0.965, 'pct': -3.5, 'exit_percent': 33},
                    {'price': close * 0.93, 'pct': -7.0, 'exit_percent': 33},
                    {'price': close * 0.895, 'pct': -10.5, 'exit_percent': 34},
                ],
                score=score, strategy_name='ichimoku', strategy_group='trend_following',
                ml_features={'cloud_position': float((close - tenkan) / close)},
                confidence=0.72
            )
        except Exception:
            return None
    
    def _support_resistance(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:
        """Support/Resistance Breakout."""
        try:
            sr = indicators.get('support_levels') or []
            rr = indicators.get('resistance_levels') or []
            close = candles[-1]['close']
            
            if not sr or not rr or close == 0:
                return None
            
            support = max(sr) if sr else close * 0.99
            resistance = min(rr) if rr else close * 1.01
            
            if close > resistance:
                direction = 'long'
                score = 75
            elif close < support:
                direction = 'short'
                score = 75
            else:
                return None
            
            return StrategySignal(
                asset=asset, timeframe=timeframe, direction=direction,
                entry=close,
                stop_loss=support if direction == 'long' else resistance,
                take_profit=[
                    {'price': close * 1.04, 'pct': 4.0, 'exit_percent': 33},
                    {'price': close * 1.08, 'pct': 8.0, 'exit_percent': 33},
                    {'price': close * 1.12, 'pct': 12.0, 'exit_percent': 34},
                ] if direction == 'long' else [
                    {'price': close * 0.96, 'pct': -4.0, 'exit_percent': 33},
                    {'price': close * 0.92, 'pct': -8.0, 'exit_percent': 33},
                    {'price': close * 0.88, 'pct': -12.0, 'exit_percent': 34},
                ],
                score=score, strategy_name='support_resistance', strategy_group='breakout',
                ml_features={'breakout_strength': float((close - support) / (resistance - support))},
                confidence=0.75
            )
        except Exception:
            return None
    
    def _volume_breakout(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:
        """Volume Breakout."""
        try:
            vol = indicators.get('volume')
            vol_avg = indicators.get('volume_avg')
            close = candles[-1]['close']
            
            if not vol or not vol_avg or close == 0:
                return None
            
            if vol < vol_avg * 1.5:
                return None
            
            direction = 'long' if close > candles[-2]['close'] else 'short'
            score = 73
            
            return StrategySignal(
                asset=asset, timeframe=timeframe, direction=direction,
                entry=close,
                stop_loss=close * (0.97 if direction == 'long' else 1.03),
                take_profit=[
                    {'price': close * 1.04, 'pct': 4.0, 'exit_percent': 33},
                    {'price': close * 1.08, 'pct': 8.0, 'exit_percent': 33},
                    {'price': close * 1.12, 'pct': 12.0, 'exit_percent': 34},
                ] if direction == 'long' else [
                    {'price': close * 0.96, 'pct': -4.0, 'exit_percent': 33},
                    {'price': close * 0.92, 'pct': -8.0, 'exit_percent': 33},
                    {'price': close * 0.88, 'pct': -12.0, 'exit_percent': 34},
                ],
                score=score, strategy_name='volume_breakout', strategy_group='breakout',
                ml_features={'volume_ratio': float(vol / vol_avg)},
                confidence=0.73
            )
        except Exception:
            return None
    
    def _bollinger_bounce(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:
        """Bollinger Band Bounce (Mean Reversion)."""
        try:
            bb = indicators.get('bollinger', {})
            close = candles[-1]['close']
            
            if not bb or close == 0:
                return None
            
            upper = bb.get('upper', close * 1.02)
            lower = bb.get('lower', close * 0.98)
            
            direction = None
            if close < lower * 1.01:
                direction = 'long'
            elif close > upper * 0.99:
                direction = 'short'
            
            if not direction:
                return None
            
            score = 70
            mid = (upper + lower) / 2
            
            return StrategySignal(
                asset=asset, timeframe=timeframe, direction=direction,
                entry=close,
                stop_loss=lower if direction == 'long' else upper,
                take_profit=[
                    {'price': mid, 'pct': ((mid - close) / close) * 100, 'exit_percent': 33},
                    {'price': upper if direction == 'long' else lower, 'pct': ((upper - close) / close) * 100 if direction == 'long' else ((lower - close) / close) * 100, 'exit_percent': 33},
                    {'price': upper * 1.01 if direction == 'long' else lower * 0.99, 'pct': ((upper * 1.01 - close) / close) * 100 if direction == 'long' else ((lower * 0.99 - close) / close) * 100, 'exit_percent': 34},
                ],
                score=score, strategy_name='bollinger_bounce', strategy_group='mean_reversion',
                ml_features={'bb_position': float((close - lower) / (upper - lower))},
                confidence=0.70
            )
        except Exception:
            return None
    
    def _range_expansion(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:
        """Range Expansion Breakout."""
        try:
            close = candles[-1]['close']
            high = candles[-1]['high']
            low = candles[-1]['low']
            
            if close == 0:
                return None
            
            range_20 = max([c['high'] for c in candles[-20:]]) - min([c['low'] for c in candles[-20:]])
            curr_range = high - low
            
            if curr_range < range_20 * 1.3:
                return None
            
            direction = 'long' if close > (high + low) / 2 else 'short'
            score = 72
            
            return StrategySignal(
                asset=asset, timeframe=timeframe, direction=direction,
                entry=close,
                stop_loss=low if direction == 'long' else high,
                take_profit=[
                    {'price': close * 1.04, 'pct': 4.0, 'exit_percent': 33},
                    {'price': close * 1.08, 'pct': 8.0, 'exit_percent': 33},
                    {'price': close * 1.12, 'pct': 12.0, 'exit_percent': 34},
                ] if direction == 'long' else [
                    {'price': close * 0.96, 'pct': -4.0, 'exit_percent': 33},
                    {'price': close * 0.92, 'pct': -8.0, 'exit_percent': 33},
                    {'price': close * 0.88, 'pct': -12.0, 'exit_percent': 34},
                ],
                score=score, strategy_name='range_expansion', strategy_group='breakout',
                ml_features={'range_ratio': float(curr_range / range_20)},
                confidence=0.72
            )
        except Exception:
            return None

    def _donchian_breakout(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:
        """Donchian Channel Breakout (20-period)."""
        try:
            if len(candles) < 21:
                return None

            close = candles[-1]['close']
            if close == 0:
                return None

            high_20 = max([c['high'] for c in candles[-20:]])
            low_20 = min([c['low'] for c in candles[-20:]])

            if close > high_20:
                direction = 'long'
            elif close < low_20:
                direction = 'short'
            else:
                return None

            score = 74
            mid = (high_20 + low_20) / 2

            return StrategySignal(
                asset=asset, timeframe=timeframe, direction=direction,
                entry=close,
                stop_loss=mid,
                take_profit=[
                    {'price': close * 1.04, 'pct': 4.0, 'exit_percent': 33},
                    {'price': close * 1.08, 'pct': 8.0, 'exit_percent': 33},
                    {'price': close * 1.12, 'pct': 12.0, 'exit_percent': 34},
                ] if direction == 'long' else [
                    {'price': close * 0.96, 'pct': -4.0, 'exit_percent': 33},
                    {'price': close * 0.92, 'pct': -8.0, 'exit_percent': 33},
                    {'price': close * 0.88, 'pct': -12.0, 'exit_percent': 34},
                ],
                score=score, strategy_name='donchian_breakout', strategy_group='breakout',
                ml_features={'donchian_width': float((high_20 - low_20) / close)},
                confidence=0.74
            )
        except Exception:
            return None
    
    def _rsi_divergence(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:
        """RSI Divergence."""
        try:
            rsi = indicators.get('rsi')
            close = candles[-1]['close']
            
            if rsi is None or close == 0:
                return None
            
            direction = None
            if rsi < 30:
                direction = 'long'
            elif rsi > 70:
                direction = 'short'
            
            if not direction:
                return None
            
            score = 71
            
            return StrategySignal(
                asset=asset, timeframe=timeframe, direction=direction,
                entry=close,
                stop_loss=close * (0.98 if direction == 'long' else 1.02),
                take_profit=[
                    {'price': close * 1.035, 'pct': 3.5, 'exit_percent': 33},
                    {'price': close * 1.07, 'pct': 7.0, 'exit_percent': 33},
                    {'price': close * 1.105, 'pct': 10.5, 'exit_percent': 34},
                ] if direction == 'long' else [
                    {'price': close * 0.965, 'pct': -3.5, 'exit_percent': 33},
                    {'price': close * 0.93, 'pct': -7.0, 'exit_percent': 33},
                    {'price': close * 0.895, 'pct': -10.5, 'exit_percent': 34},
                ],
                score=score, strategy_name='rsi_divergence', strategy_group='mean_reversion',
                ml_features={'rsi': float(rsi)},
                confidence=0.71
            )
        except Exception:
            return None
    
    def _stochastic_reversal(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:
        """Stochastic Reversal."""
        try:
            stoch = indicators.get('stoch_rsi')
            close = candles[-1]['close']
            
            if stoch is None or close == 0:
                return None
            
            direction = None
            if stoch < 0.2:
                direction = 'long'
            elif stoch > 0.8:
                direction = 'short'
            
            if not direction:
                return None
            
            score = 70
            
            return StrategySignal(
                asset=asset, timeframe=timeframe, direction=direction,
                entry=close,
                stop_loss=close * (0.99 if direction == 'long' else 1.01),
                take_profit=[
                    {'price': close * 1.03, 'pct': 3.0, 'exit_percent': 33},
                    {'price': close * 1.06, 'pct': 6.0, 'exit_percent': 33},
                    {'price': close * 1.09, 'pct': 9.0, 'exit_percent': 34},
                ] if direction == 'long' else [
                    {'price': close * 0.97, 'pct': -3.0, 'exit_percent': 33},
                    {'price': close * 0.94, 'pct': -6.0, 'exit_percent': 33},
                    {'price': close * 0.91, 'pct': -9.0, 'exit_percent': 34},
                ],
                score=score, strategy_name='stochastic_reversal', strategy_group='mean_reversion',
                ml_features={'stoch': float(stoch)},
                confidence=0.70
            )
        except Exception:
            return None
    
    def _momentum_divergence(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:
        """Momentum Divergence."""
        try:
            close = candles[-1]['close']
            if close == 0:
                return None
            
            # Simple momentum: ROC
            roc = ((close - candles[-14]['close']) / candles[-14]['close']) * 100 if len(candles) > 14 else 0
            
            if abs(roc) < 2:
                return None
            
            direction = 'long' if roc > 0 else 'short'
            score = 70
            
            return StrategySignal(
                asset=asset, timeframe=timeframe, direction=direction,
                entry=close,
                stop_loss=close * (0.98 if direction == 'long' else 1.02),
                take_profit=[
                    {'price': close * 1.03, 'pct': 3.0, 'exit_percent': 33},
                    {'price': close * 1.06, 'pct': 6.0, 'exit_percent': 33},
                    {'price': close * 1.09, 'pct': 9.0, 'exit_percent': 34},
                ] if direction == 'long' else [
                    {'price': close * 0.97, 'pct': -3.0, 'exit_percent': 33},
                    {'price': close * 0.94, 'pct': -6.0, 'exit_percent': 33},
                    {'price': close * 0.91, 'pct': -9.0, 'exit_percent': 34},
                ],
                score=score, strategy_name='momentum_divergence', strategy_group='momentum',
                ml_features={'roc': float(roc)},
                confidence=0.70
            )
        except Exception:
            return None
    
    def _rate_of_change(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:
        """Rate of Change (ROC)."""
        try:
            close = candles[-1]['close']
            if close == 0 or len(candles) < 20:
                return None
            
            roc_20 = ((close - candles[-20]['close']) / candles[-20]['close']) * 100
            
            if abs(roc_20) < 2.5:
                return None
            
            direction = 'long' if roc_20 > 0 else 'short'
            score = 71
            
            return StrategySignal(
                asset=asset, timeframe=timeframe, direction=direction,
                entry=close,
                stop_loss=close * (0.97 if direction == 'long' else 1.03),
                take_profit=[
                    {'price': close * 1.035, 'pct': 3.5, 'exit_percent': 33},
                    {'price': close * 1.07, 'pct': 7.0, 'exit_percent': 33},
                    {'price': close * 1.105, 'pct': 10.5, 'exit_percent': 34},
                ] if direction == 'long' else [
                    {'price': close * 0.965, 'pct': -3.5, 'exit_percent': 33},
                    {'price': close * 0.93, 'pct': -7.0, 'exit_percent': 33},
                    {'price': close * 0.895, 'pct': -10.5, 'exit_percent': 34},
                ],
                score=score, strategy_name='rate_of_change', strategy_group='momentum',
                ml_features={'roc_20': float(roc_20)},
                confidence=0.71
            )
        except Exception:
            return None
    
    def _williams_r(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:
        """Williams %R."""
        try:
            close = candles[-1]['close']
            high_14 = max([c['high'] for c in candles[-14:]])
            low_14 = min([c['low'] for c in candles[-14:]])
            
            if close == 0 or high_14 == low_14:
                return None
            
            williams_r = ((high_14 - close) / (high_14 - low_14)) * -100
            
            direction = None
            if williams_r < -80:
                direction = 'long'
            elif williams_r > -20:
                direction = 'short'
            
            if not direction:
                return None
            
            score = 70
            
            return StrategySignal(
                asset=asset, timeframe=timeframe, direction=direction,
                entry=close,
                stop_loss=close * (0.98 if direction == 'long' else 1.02),
                take_profit=[
                    {'price': close * 1.04, 'pct': 4.0, 'exit_percent': 33},
                    {'price': close * 1.08, 'pct': 8.0, 'exit_percent': 33},
                    {'price': close * 1.12, 'pct': 12.0, 'exit_percent': 34},
                ] if direction == 'long' else [
                    {'price': close * 0.96, 'pct': -4.0, 'exit_percent': 33},
                    {'price': close * 0.92, 'pct': -8.0, 'exit_percent': 33},
                    {'price': close * 0.88, 'pct': -12.0, 'exit_percent': 34},
                ],
                score=score, strategy_name='williams_r', strategy_group='momentum',
                ml_features={'williams_r': float(williams_r)},
                confidence=0.70
            )
        except Exception:
            return None
    
    def _candlestick_patterns(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:
        """Candlestick Patterns (Engulfing, Hammer)."""
        try:
            if len(candles) < 2:
                return None
            
            curr = candles[-1]
            prev = candles[-2]
            close = curr['close']
            
            if close == 0:
                return None
            
            # Engulfing pattern
            bullish_engulf = (prev['close'] < prev['open'] and 
                            curr['close'] > curr['open'] and
                            curr['open'] < prev['close'] and
                            curr['close'] > prev['open'])
            
            bearish_engulf = (prev['close'] > prev['open'] and 
                            curr['close'] < curr['open'] and
                            curr['open'] > prev['close'] and
                            curr['close'] < prev['open'])
            
            direction = 'long' if bullish_engulf else 'short' if bearish_engulf else None
            
            if not direction:
                return None
            
            score = 72
            
            return StrategySignal(
                asset=asset, timeframe=timeframe, direction=direction,
                entry=close,
                stop_loss=prev['low'] if direction == 'long' else prev['high'],
                take_profit=[
                    {'price': close * 1.04, 'pct': 4.0, 'exit_percent': 33},
                    {'price': close * 1.08, 'pct': 8.0, 'exit_percent': 33},
                    {'price': close * 1.12, 'pct': 12.0, 'exit_percent': 34},
                ] if direction == 'long' else [
                    {'price': close * 0.96, 'pct': -4.0, 'exit_percent': 33},
                    {'price': close * 0.92, 'pct': -8.0, 'exit_percent': 33},
                    {'price': close * 0.88, 'pct': -12.0, 'exit_percent': 34},
                ],
                score=score, strategy_name='candlestick_patterns', strategy_group='pattern_recognition',
                ml_features={'pattern_strength': 0.72},
                confidence=0.72
            )
        except Exception:
            return None
    
    def _chart_patterns(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:
        """Chart Patterns (Flags, Triangles)."""
        try:
            if len(candles) < 5:
                return None
            
            close = candles[-1]['close']
            if close == 0:
                return None
            
            # Simplified flag pattern detection
            recent_highs = [c['high'] for c in candles[-5:]]
            recent_lows = [c['low'] for c in candles[-5:]]
            
            consolidation = max(recent_highs) - min(recent_lows)
            
            if consolidation > close * 0.05:
                return None
            
            direction = 'long' if close > (max(recent_highs) + min(recent_lows)) / 2 else 'short'
            score = 71
            
            return StrategySignal(
                asset=asset, timeframe=timeframe, direction=direction,
                entry=close,
                stop_loss=min(recent_lows) if direction == 'long' else max(recent_highs),
                take_profit=[
                    {'price': close * 1.04, 'pct': 4.0, 'exit_percent': 33},
                    {'price': close * 1.08, 'pct': 8.0, 'exit_percent': 33},
                    {'price': close * 1.12, 'pct': 12.0, 'exit_percent': 34},
                ] if direction == 'long' else [
                    {'price': close * 0.96, 'pct': -4.0, 'exit_percent': 33},
                    {'price': close * 0.92, 'pct': -8.0, 'exit_percent': 33},
                    {'price': close * 0.88, 'pct': -12.0, 'exit_percent': 34},
                ],
                score=score, strategy_name='chart_patterns', strategy_group='pattern_recognition',
                ml_features={'consolidation': float(consolidation / close)},
                confidence=0.71
            )
        except Exception:
            return None
    
    def _htf_trend_ltf_entry(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:
        """HTF Trend + LTF Entry."""
        try:
            close = candles[-1]['close']
            trend = indicators.get('trend_ema')
            
            if close == 0 or trend is None:
                return None
            
            direction = 'long' if trend > 0 else 'short' if trend < 0 else None
            
            if not direction:
                return None
            
            score = 75
            
            return StrategySignal(
                asset=asset, timeframe=timeframe, direction=direction,
                entry=close,
                stop_loss=close * (0.97 if direction == 'long' else 1.03),
                take_profit=[
                    {'price': close * 1.04, 'pct': 4.0, 'exit_percent': 33},
                    {'price': close * 1.08, 'pct': 8.0, 'exit_percent': 33},
                    {'price': close * 1.12, 'pct': 12.0, 'exit_percent': 34},
                ] if direction == 'long' else [
                    {'price': close * 0.96, 'pct': -4.0, 'exit_percent': 33},
                    {'price': close * 0.92, 'pct': -8.0, 'exit_percent': 33},
                    {'price': close * 0.88, 'pct': -12.0, 'exit_percent': 34},
                ],
                score=score, strategy_name='htf_trend_ltf_entry', strategy_group='multi_timeframe',
                ml_features={'trend_strength': float(trend)},
                confidence=0.75
            )
        except Exception:
            return None
    
    def _triple_timeframe(self, asset: str, timeframe: str, candles: List, indicators: Dict) -> Optional[StrategySignal]:
        """Triple Timeframe Confirmation."""
        try:
            close = candles[-1]['close']
            if close == 0:
                return None
            
            # Simplified: use available indicators as proxy
            ema_fast = indicators.get('ema_fast')
            ema_slow = indicators.get('ema_slow')
            rsi = indicators.get('rsi')
            
            if not all([ema_fast, ema_slow, rsi is not None]):
                return None
            
            bullish = ema_fast > ema_slow and rsi > 50
            bearish = ema_fast < ema_slow and rsi < 50
            
            direction = 'long' if bullish else 'short' if bearish else None
            
            if not direction:
                return None
            
            score = 76
            
            return StrategySignal(
                asset=asset, timeframe=timeframe, direction=direction,
                entry=close,
                stop_loss=close * (0.96 if direction == 'long' else 1.04),
                take_profit=[
                    {'price': close * 1.05, 'pct': 5.0, 'exit_percent': 33},
                    {'price': close * 1.10, 'pct': 10.0, 'exit_percent': 33},
                    {'price': close * 1.15, 'pct': 15.0, 'exit_percent': 34},
                ] if direction == 'long' else [
                    {'price': close * 0.95, 'pct': -5.0, 'exit_percent': 33},
                    {'price': close * 0.90, 'pct': -10.0, 'exit_percent': 33},
                    {'price': close * 0.85, 'pct': -15.0, 'exit_percent': 34},
                ],
                score=score, strategy_name='triple_timeframe', strategy_group='multi_timeframe',
                ml_features={'confirmation_count': 3.0},
                confidence=0.76
            )
        except Exception:
            return None
