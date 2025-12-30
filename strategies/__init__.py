from .trend import trend_strategies
from .momentum import momentum_strategies
from .volatility import volatility_strategies
from .structure import structure_strategy

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
    for timeframe, data in market_data.items():
        # Only allow lower timeframe trades in direction of HTF bias
        if timeframe in ["5m", "15m", "1h"] and htf_bias:
            allowed_direction = htf_bias
        else:
            allowed_direction = None
        # Determine which groups to run based on regime_strategies (if provided)
        groups = []
        if regime_strategies and regime in regime_strategies:
            groups = regime_strategies[regime]
        else:
            if regime == "TRENDING":
                groups = ["trend", "structure"]
            elif regime == "RANGING":
                groups = ["momentum", "structure"]
            elif regime == "VOLATILE":
                groups = ["volatility", "structure"]
            else:
                groups = ["structure"]
        if "trend" in groups:
            for sig in trend_strategies(asset, timeframe, data):
                if allowed_direction and sig.get('direction') != allowed_direction:
                    continue
                if not strategy_weights or strategy_weights.get(sig.get('strategy', sig.get('name', '')), 1) > 0:
                    sig['weight'] = strategy_weights.get(sig.get('strategy', sig.get('name', '')), 1) if strategy_weights else 1
                    signals.append(sig)
        if "momentum" in groups:
            for sig in momentum_strategies(asset, timeframe, data):
                if allowed_direction and sig.get('direction') != allowed_direction:
                    continue
                if not strategy_weights or strategy_weights.get(sig.get('strategy', sig.get('name', '')), 1) > 0:
                    sig['weight'] = strategy_weights.get(sig.get('strategy', sig.get('name', '')), 1) if strategy_weights else 1
                    signals.append(sig)
        if "volatility" in groups:
            for sig in volatility_strategies(asset, timeframe, data):
                if allowed_direction and sig.get('direction') != allowed_direction:
                    continue
                if not strategy_weights or strategy_weights.get(sig.get('strategy', sig.get('name', '')), 1) > 0:
                    sig['weight'] = strategy_weights.get(sig.get('strategy', sig.get('name', '')), 1) if strategy_weights else 1
                    signals.append(sig)
        if "structure" in groups:
            for sig in structure_strategy(asset, timeframe, data):
                if allowed_direction and sig.get('direction') != allowed_direction:
                    continue
                if not strategy_weights or strategy_weights.get(sig.get('strategy', sig.get('name', '')), 1) > 0:
                    sig['weight'] = strategy_weights.get(sig.get('strategy', sig.get('name', '')), 1) if strategy_weights else 1
                    signals.append(sig)
    return signals
