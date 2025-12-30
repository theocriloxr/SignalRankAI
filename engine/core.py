from data.fetcher import fetch_market_data
from engine.regime import detect_market_regime
from strategies import run_all_strategies
from engine.consensus import apply_consensus_filter
from engine.risk import calculate_dynamic_risk
from engine.scoring import calculate_signal_score
from db.database import store_signal
from engine.ranking import rank_signals
from signalrank_telegram.bot import dispatch_signals

MIN_SCORE_THRESHOLD = 75

def load_tradable_assets():
    # Example: Replace with real asset loader
    return ['BTCUSDT', 'ETHUSD', 'EURUSD', 'GBPUSD']

def main_loop():
    timeframes = ['5m', '15m', '1h', '4h', '1d']
    assets = get_all_trending_pairs()
    for asset in assets:
        market_data = fetch_market_data(asset, timeframes)
        regime = detect_market_regime(market_data)
        strategy_signals = run_all_strategies(asset, market_data, regime)
        consensus_signals = apply_consensus_filter(strategy_signals)
        for signal in consensus_signals:
            risk_profile = calculate_dynamic_risk(signal, regime)
            score = calculate_signal_score(signal, risk_profile, regime)
            if score >= MIN_SCORE_THRESHOLD:
                signal['score'] = score
                signal['risk_profile'] = risk_profile
                store_signal(signal)
    ranked_signals = rank_signals()
    dispatch_signals(ranked_signals)
