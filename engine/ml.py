# ML weighting: returns a dict of {strategy_name: weight}
def get_strategy_weights():
    # TODO: Replace with real ML/DB logic
    return {
        'EMA Trend': 1.0,
        'Supertrend': 1.0,
        'ADX Trend': 1.0,
        'RSI Momentum': 1.0,
        'MACD Momentum': 1.0,
        'Stoch RSI Momentum': 1.0,
        'ATR Breakout': 1.0,
        'BB Width Volatility': 1.0,
        'Keltner Volatility': 1.0,
        'Structure Bull': 1.0,
        'S/R Break + Retest': 1.0,
        'Liquidity Sweep': 1.0
    }

# Regime-based strategy group activation
def get_regime_strategies():
    # TODO: Replace with real ML/DB logic
    return {
        'TRENDING': ['trend', 'structure'],
        'RANGING': ['momentum', 'structure'],
        'VOLATILE': ['volatility', 'structure'],
        'NEUTRAL': ['structure']
    }
# ML auto-learning hook (weekly job)
from db.database import get_unreleased_signals

def adjust_weight_based_on_performance(strategy):
    # Placeholder: adjust strategy weights based on winrate, drawdown, etc.
    pass

def disable_strategies_with_drawdown():
    # Placeholder: disable strategies with high drawdown
    pass

def weekly_job():
    stats = get_unreleased_signals()  # Replace with real outcome stats
    # For each strategy, adjust weights
    for strategy in set(s['strategy_name'] for s in stats):
        adjust_weight_based_on_performance(strategy)
    disable_strategies_with_drawdown()
