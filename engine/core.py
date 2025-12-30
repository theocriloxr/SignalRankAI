from data.fetcher import fetch_market_data
from data.pair_discovery import get_all_trending_pairs
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

def main_loop(DRY_RUN=False):
    timeframes = ['5m', '15m', '1h', '4h', '1d']
    assets = get_all_trending_pairs()
    # Example: fetch strategy weights and regime_strategies from ML/DB (stubbed here)
    from engine.ml import get_strategy_weights, get_regime_strategies
    strategy_weights = get_strategy_weights() if hasattr(get_strategy_weights, '__call__') else {}
    regime_strategies = get_regime_strategies() if hasattr(get_regime_strategies, '__call__') else None
    for asset in assets:
        market_data = fetch_market_data(asset, timeframes)
        regime = detect_market_regime(market_data)
        strategy_signals = run_all_strategies(asset, market_data, regime, strategy_weights=strategy_weights, regime_strategies=regime_strategies)
        # Signal Controller step (deduplication)
        from engine.signal_controller import SignalController
        controller = SignalController()
        filtered_signals = []
        for signal in strategy_signals:
            if signal and controller.can_emit(signal):
                controller.register(signal)
                filtered_signals.append(signal)
        controller.reset_cycle()
        # Consensus Engine
        from engine.consensus import consensus_filter
        consensus_signals = consensus_filter(filtered_signals)
        # Risk Engine
        from engine.risk import risk_check
        account_state = type('AccountState', (), {'drawdown': 0.0})()  # Replace with real account state
        risk_signals = [s for s in consensus_signals if risk_check(s, account_state)]

        # ML Probability Filter
        from ml.features import extract_features
        from ml.inference import MLFilter
        ml_filter = MLFilter()
        ml_signals = []
        for signal in risk_signals:
            features = extract_features(signal, market_data)
            try:
                approved, probability = ml_filter.ml_filter(features)
            except Exception:
                approved, probability = True, None
            if not approved:
                # Optionally log rejection
                continue
            signal["ml_probability"] = probability
            ml_signals.append(signal)

        # Scoring
        from engine.scoring import score_signal
        scored_signals = []
        for signal in ml_signals:
            score = score_signal(signal)
            signal['score'] = score
            if score >= MIN_SCORE_THRESHOLD:
                scored_signals.append(signal)
                store_signal(signal)
    # Ranking and Dispatch
    from engine.ranking import rank_signals
    ranked_signals = rank_signals()
    all_signals = ranked_signals.get('vip', []) + ranked_signals.get('premium', [])
    if DRY_RUN:
        for signal in all_signals:
            print("[DRY RUN]", signal)
    else:
        from signalrank_telegram.bot import dispatch_signals
        # Replace with real user_id in production
        dispatch_signals(all_signals, user_id=123456789)
