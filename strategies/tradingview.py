"""
TradingView Technical Analysis Integration

Integrates tradingview-ta library for technical analysis signals.
Uses TradingView's comprehensive indicator analysis without API key limitations.

Installation:
    pip install tradingview-ta

Features:
- 30+ technical indicators analyzed
- Support for crypto and forex
- Multiple timeframes
- Screener for market-wide analysis
"""

import os
import logging
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_RATE_LIMIT = "__TV_RATE_LIMIT__"


def _env_bool(name: str, default: bool = False) -> bool:
    """Parse environment variable as boolean."""
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    """Parse environment variable as float."""
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


def _env_int(name: str, default: int) -> int:
    """Parse environment variable as int."""
    try:
        return int((os.getenv(name) or str(default)).strip())
    except Exception:
        return int(default)


def get_tradingview_signals(asset: str, timeframe: str) -> list[dict]:
    """
    Fetch technical signals from TradingView for an asset and timeframe.
    
    Args:
        asset: Trading pair (e.g., 'BTCUSDT', 'EURUSD')
        timeframe: Timeframe (e.g., '1h', '4h', '1d', '5m', '15m')
    
    Returns:
        List of signal dicts with direction, confidence, entry, stop, targets
    """
    signals = []
    
    # Check if TradingView integration is enabled
    if not _env_bool("TRADINGVIEW_ENABLED", False):
        return signals
    
    try:
        from tradingview_ta import TA_Handler, Interval
        
        # Normalize timeframe to tradingview format
        tf_map = {
            '1m': Interval.INTERVAL_1_MINUTE,
            '5m': Interval.INTERVAL_5_MINUTES,
            '15m': Interval.INTERVAL_15_MINUTES,
            '1h': Interval.INTERVAL_1_HOUR,
            '4h': Interval.INTERVAL_4_HOURS,
            '1d': Interval.INTERVAL_1_DAY,
            '1w': Interval.INTERVAL_1_WEEK,
        }
        
        tv_tf = tf_map.get(timeframe.lower().strip())
        if tv_tf is None:
            logger.warning(f"[tradingview] Unsupported timeframe: {timeframe}")
            return signals
        
        # Determine exchange (crypto or forex)
        # Crypto: keep full symbol (BTCUSDT) on BINANCE screener
        asset_upper = (asset or "").upper().strip()
        if asset_upper.endswith(('USDT', 'BUSD', 'USDC', 'BTC', 'ETH')):
            exchange = 'BINANCE'
            symbol = asset_upper  # TradingView expects full pair, e.g., BTCUSDT
        elif len(asset_upper) == 6 and asset_upper.isalpha():
            # Forex pair (e.g., EURUSD, GBPUSD)
            exchange = 'FX_IDC'
            symbol = asset_upper
        else:
            logger.warning(f"[tradingview] Unknown asset type: {asset}")
            return signals
        
        # Fetch analysis with graceful fallback for unsupported symbols
        screener = 'forex' if exchange == 'FX_IDC' else 'crypto'
        logger.info(f"[tradingview] source=tradingview asset={asset_upper} symbol={symbol} exchange={exchange} screener={screener} tf={timeframe}")
        handler = TA_Handler(
            symbol=symbol,
            screener=screener,
            exchange=exchange,
            interval=tv_tf,
        )

        max_rl_retries = max(1, _env_int("TRADINGVIEW_RATE_LIMIT_RETRIES", 2))
        rl_delay = _env_float("TRADINGVIEW_RATE_LIMIT_DELAY", 3.0)

        def _try_analysis(h):
            try:
                return h.get_analysis()
            except Exception as exc:
                err_msg = str(exc).lower()
                if "exchange or symbol not found" in err_msg:
                    return None
                if "status code: 429" in err_msg or "http status code: 429" in err_msg:
                    return _RATE_LIMIT
                raise

        def _run_with_rate_limit(h, label: str):
            for attempt in range(1, max_rl_retries + 1):
                result = _try_analysis(h)
                if result != _RATE_LIMIT:
                    return result
                if attempt < max_rl_retries:
                    logger.warning(
                        f"[tradingview] rate_limited symbol={label} attempt={attempt}/{max_rl_retries} sleep={rl_delay}s"
                    )
                    time.sleep(rl_delay)
            logger.error(
                f"[tradingview] rate_limit_exhausted symbol={label} retries={max_rl_retries}"
            )
            return _RATE_LIMIT

        analysis = _run_with_rate_limit(handler, symbol)
        # Fallback: some TradingView listings require base-only symbol (rare). Try that once.
        if analysis is None and asset_upper.endswith("USDT"):
            base_only = asset_upper[:-4]
            logger.warning(f"[tradingview] retry_base_only asset={asset_upper} base={base_only} exchange={exchange} tf={timeframe}")
            try:
                handler2 = TA_Handler(
                    symbol=base_only,
                    screener=screener,
                    exchange=exchange,
                    interval=tv_tf,
                )
                analysis = _run_with_rate_limit(handler2, base_only)
            except Exception:
                analysis = None

        if analysis == _RATE_LIMIT:
            return signals

        if analysis is None:
            logger.warning(f"[tradingview] skip symbol_not_found asset={asset_upper} exchange={exchange} tf={timeframe}")
            return signals
        
        # Extract recommendation
        recommendation = getattr(analysis, 'recommendation', 'NEUTRAL').upper()
        
        # Count indicator votes for confidence calculation
        indicators = getattr(analysis, 'indicators', {})
        
        oscillators = indicators.get('oscillators', {})
        moving_averages = indicators.get('moving_averages', {})
        
        oscillator_summary = oscillators.get('summary', {})
        ma_summary = moving_averages.get('summary', {})
        
        oscillator_signal = oscillator_summary.get('signal', 'NEUTRAL').upper()
        ma_signal = ma_summary.get('signal', 'NEUTRAL').upper()
        
        # Count STRONG_BUY/BUY votes
        buy_votes = 0
        sell_votes = 0
        neutral_votes = 0
        
        for ind_name, ind_data in oscillators.items():
            if ind_name == 'summary':
                continue
            if isinstance(ind_data, dict):
                val = ind_data.get('value', 'NEUTRAL')
            else:
                val = str(ind_data).upper()
            
            if 'BUY' in val:
                buy_votes += 2 if 'STRONG' in val else 1
            elif 'SELL' in val:
                sell_votes += 2 if 'STRONG' in val else 1
            else:
                neutral_votes += 1
        
        for ind_name, ind_data in moving_averages.items():
            if ind_name == 'summary':
                continue
            if isinstance(ind_data, dict):
                val = ind_data.get('value', 'NEUTRAL')
            else:
                val = str(ind_data).upper()
            
            if 'BUY' in val:
                buy_votes += 1
            elif 'SELL' in val:
                sell_votes += 1
            else:
                neutral_votes += 1
        
        total_votes = buy_votes + sell_votes + neutral_votes
        if total_votes == 0:
            return signals
        
        # Calculate confidence: higher vote count = more confident
        # 70% votes for direction = 0.7 confidence, etc.
        buy_confidence = (buy_votes / total_votes) if total_votes > 0 else 0.0
        sell_confidence = (sell_votes / total_votes) if total_votes > 0 else 0.0
        
        # Require minimum 40% agreement (at least 4 out of 10 indicators)
        min_confidence = _env_float("TRADINGVIEW_MIN_CONFIDENCE", 0.40)
        
        # BUY Signal
        if recommendation in ('BUY', 'STRONG_BUY') and buy_confidence >= min_confidence:
            signal = _create_signal(
                direction='BUY',
                asset=asset,
                timeframe=timeframe,
                confidence=min(0.95, 0.50 + (buy_confidence - min_confidence) * 0.5),
                oscillator_signal=oscillator_signal,
                ma_signal=ma_signal,
                strategy_name='TradingView Multi-Indicator',
            )
            if signal:
                signals.append(signal)
        
        # SELL Signal
        elif recommendation in ('SELL', 'STRONG_SELL') and sell_confidence >= min_confidence:
            signal = _create_signal(
                direction='SELL',
                asset=asset,
                timeframe=timeframe,
                confidence=min(0.95, 0.50 + (sell_confidence - min_confidence) * 0.5),
                oscillator_signal=oscillator_signal,
                ma_signal=ma_signal,
                strategy_name='TradingView Multi-Indicator',
            )
            if signal:
                signals.append(signal)
        
        logger.info(
            f"[tradingview] {asset} {timeframe}: "
            f"rec={recommendation} buy={buy_votes}/{total_votes} sell={sell_votes}/{total_votes}"
        )
        
    except ImportError:
        logger.warning(
            "[tradingview] tradingview-ta not installed. Install with: pip install tradingview-ta"
        )
    except Exception as e:
        logger.error(f"[tradingview] Error analyzing {asset} {timeframe}: {e}", exc_info=True)
    
    return signals


def _create_signal(direction: str, asset: str, timeframe: str, confidence: float,
                   oscillator_signal: str, ma_signal: str, strategy_name: str) -> dict | None:
    """
    Create a signal dict from TradingView analysis.
    
    Note: TradingView doesn't provide entry/stop/target, so we use price action ATR-based sizing.
    """
    try:
        from data.fetcher import get_candles
        from data.indicators import calculate_atr
        
        # Fetch recent candles for entry/stop/target calculation
        candles = get_candles(asset, timeframe, limit=100)
        if not candles or len(candles) < 20:
            return None
        
        # Use recent close as entry point
        entry = float(candles[-1]['close'])
        
        # Calculate ATR for stop sizing
        atr = calculate_atr(candles, period=14)
        if atr is None or atr <= 0:
            atr = entry * 0.02  # Fallback: 2% ATR
        
        # Position sizing based on timeframe (longer TFs = wider stops)
        tf_multiplier = {
            '5m': 1.5,
            '15m': 1.5,
            '1h': 2.0,
            '4h': 2.5,
            '1d': 3.0,
            '1w': 4.0,
        }
        multiplier = tf_multiplier.get(timeframe.lower(), 2.0)
        
        # Generate signal
        if direction == 'BUY':
            stop = entry - (atr * multiplier)
            # Target 2:1 R/R
            target = entry + (entry - stop) * 2
        else:  # SELL
            stop = entry + (atr * multiplier)
            # Target 2:1 R/R
            target = entry - (stop - entry) * 2
        
        # Confidence boosts
        confidence_boost = 1.0
        if oscillator_signal == 'BUY' and direction == 'BUY':
            confidence_boost += 0.10
        elif oscillator_signal == 'SELL' and direction == 'SELL':
            confidence_boost += 0.10
        
        if ma_signal == 'BUY' and direction == 'BUY':
            confidence_boost += 0.10
        elif ma_signal == 'SELL' and direction == 'SELL':
            confidence_boost += 0.10
        
        final_confidence = min(0.95, confidence * confidence_boost)
        
        return {
            'direction': direction,
            'asset': asset,
            'symbol': asset,
            'timeframe': timeframe,
            'entry': entry,
            'stop': stop,
            'stop_loss': stop,
            'targets': target,
            'take_profit': target,
            'confidence': final_confidence,
            'strength': final_confidence,
            'strategy_name': strategy_name,
            'strategy_group': 'tradingview',
            'volatility': (atr / entry) if entry > 0 else 0.0,
            'source': 'tradingview-ta',
            'rr_estimate': abs((target - entry) / (entry - stop)) if (entry - stop) != 0 else 2.0,
        }
    
    except Exception as e:
        logger.error(f"[tradingview] Error creating signal for {asset}: {e}")
        return None


def tradingview_strategies(asset: str, timeframe: str, market_data: dict) -> list[dict]:
    """
    Wrapper function for integration into strategy pipeline.
    
    Args:
        asset: Trading pair
        timeframe: Timeframe
        market_data: Dict with candles and indicators (not used here, using API instead)
    
    Returns:
        List of signals from TradingView analysis
    """
    return get_tradingview_signals(asset, timeframe)


# Test/demo function
if __name__ == "__main__":
    # Example usage
    os.environ["TRADINGVIEW_ENABLED"] = "true"
    
    signals = get_tradingview_signals("BTCUSDT", "1h")
    for sig in signals:
        print(f"Signal: {sig}")
