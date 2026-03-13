import os


def _env_bool(name: str, default: bool) -> bool:
    try:
        raw = (os.getenv(name) or str(default)).strip().lower()
        return raw in {"1", "true", "yes", "on"}
    except Exception:
        return default

from .trend import trend_strategies
from .momentum import momentum_strategies
from .volatility import volatility_strategies
from .structure import structure_strategy

# Optional TradingView integration
try:
    from .tradingview import tradingview_strategies
    TRADINGVIEW_AVAILABLE = True
except ImportError:
    TRADINGVIEW_AVAILABLE = False
    tradingview_strategies = None

def run_all_strategies(asset, market_data, regime, strategy_weights=None, regime_strategies=None):
    signals = []
    # Multi-timeframe bias: get higher timeframe (HTF) bias for each asset
    def get_htf_bias(market_data):
        # Use 4h or 1d as HTF, fallback to None
        for tf in ["1d", "4h"]:
            if tf in market_data and 'indicators' in market_data[tf]:
                ind = market_data[tf]['indicators']
                # Example: use EMA or trend indicator for bias
                if ind.get('ema_fast', 0) > ind.get('ema_slow', 0):
                    return 'BUY'
                elif ind.get('ema_fast', 0) < ind.get('ema_slow', 0):
                    return 'SELL'
        return None

    htf_bias = get_htf_bias(market_data)

    # Normalize htf_bias to the direction labels used across the codebase
    # (strategies now emit 'LONG'/'SHORT'; htf_bias came from old 'BUY'/'SELL' EMA check)
    if htf_bias == 'BUY':
        htf_bias = 'LONG'
    elif htf_bias == 'SELL':
        htf_bias = 'SHORT'

    run_all = _env_bool("RUN_ALL_STRATEGIES", True)
    from .stock import stock_strategies

    # Direction normalization: strategies may emit 'BUY'/'SELL' (old) or
    # 'LONG'/'SHORT' (new). Normalize to 'LONG'/'SHORT'.
    _DIR_MAP = {'BUY': 'LONG', 'SELL': 'SHORT', 'LONG': 'LONG', 'SHORT': 'SHORT'}

    for timeframe, data in market_data.items():
        if not isinstance(data, dict):
            continue
        if 'indicators' not in data or 'candles' not in data:
            continue

        # Only allow lower timeframe trades in direction of HTF bias
        if timeframe in ["5m", "15m", "1h"] and htf_bias:
            allowed_direction = htf_bias
        else:
            allowed_direction = None

        # Determine which groups to run.
        # Default: run ALL strategy groups, then let consensus + scoring pick the winner.
        if run_all:
            groups = ["trend", "momentum", "volatility", "structure", "stock", "tradingview"]
        else:
            groups = []
            if regime_strategies and regime in regime_strategies:
                groups = regime_strategies[regime]
            else:
                if regime == "TRENDING":
                    groups = ["trend", "structure", "tradingview"]
                elif regime == "RANGING":
                    groups = ["momentum", "structure", "tradingview"]
                elif regime == "VOLATILE":
                    groups = ["volatility", "structure", "tradingview"]
                else:
                    groups = ["structure", "tradingview"]

        def _add(sig):
            """Normalize direction, apply HTF filter and weight, then append."""
            sig['direction'] = _DIR_MAP.get(str(sig.get('direction', '') or '').upper(), sig.get('direction', 'LONG'))
            if allowed_direction and sig.get('direction') != allowed_direction:
                return
            if not strategy_weights or strategy_weights.get(sig.get('strategy', sig.get('name', '')), 1) > 0:
                sig['weight'] = strategy_weights.get(sig.get('strategy', sig.get('name', '')), 1) if strategy_weights else 1
                signals.append(sig)

        if "trend" in groups:
            for sig in trend_strategies(asset, timeframe, data):
                _add(sig)
        if "stock" in groups:
            for sig in stock_strategies(asset, timeframe, data):
                _add(sig)
        if "momentum" in groups:
            for sig in momentum_strategies(asset, timeframe, data):
                _add(sig)
        if "volatility" in groups:
            for sig in volatility_strategies(asset, timeframe, data):
                _add(sig)
        if "structure" in groups:
            for sig in structure_strategy(asset, timeframe, data):
                _add(sig)
        if "tradingview" in groups and TRADINGVIEW_AVAILABLE:
            try:
                for sig in tradingview_strategies(asset, timeframe, data):
                    _add(sig)
            except Exception as e:
                try:
                    import logging
                    logging.getLogger(__name__).error(f"TradingView strategy error: {e}")
                except Exception:
                    pass
    
    return signals
