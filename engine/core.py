import os
import time

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
from core.redis_state import state

MIN_SCORE_THRESHOLD = 75

def load_tradable_assets():
    # Example: Replace with real asset loader
    return ['BTCUSDT', 'ETHUSD', 'EURUSD', 'GBPUSD']

def main_loop(DRY_RUN=False):
    timeframes = ['5m', '15m', '1h', '4h', '1d']
    cycle_sleep_seconds = int(os.getenv("CYCLE_SLEEP_SECONDS", "60"))

    # Example: fetch strategy weights and regime_strategies from ML/DB (stubbed here)
    from engine.ml import get_strategy_weights, get_regime_strategies
    strategy_weights = get_strategy_weights() if hasattr(get_strategy_weights, '__call__') else {}
    regime_strategies = get_regime_strategies() if hasattr(get_regime_strategies, '__call__') else None

    while True:
        # Global kill-switch (skip cycle but keep process alive)
        try:
            if state.get_killswitch_sync().enabled:
                time.sleep(max(5, cycle_sleep_seconds))
                continue
        except Exception:
            pass

        try:
            try:
                assets = get_all_trending_pairs() or []
            except Exception:
                assets = []

            if not assets:
                assets = load_tradable_assets()

            scored_signals_all = []

            for asset in assets:
                try:
                    market_data = fetch_market_data(asset, timeframes)
                    regime = detect_market_regime(market_data)
                    strategy_signals = run_all_strategies(
                        asset,
                        market_data,
                        regime,
                        strategy_weights=strategy_weights,
                        regime_strategies=regime_strategies,
                    )

                    # Signal Controller step (deduplication + normalization)
                    from engine.signal_controller import SignalController

                    controller = SignalController()
                    filtered_signals = controller.deduplicate_signals(strategy_signals)

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
                            continue
                        signal["ml_probability"] = probability
                        ml_signals.append(signal)

                    # Scoring
                    from engine.scoring import score_signal

                    for signal in ml_signals:
                        score = score_signal(signal)
                        signal['score'] = score
                        if score >= MIN_SCORE_THRESHOLD:
                            # Normalize for DB + formatters
                            signal['regime'] = regime
                            signal['stop_loss'] = signal.get('stop_loss', signal.get('stop'))
                            signal['take_profit'] = signal.get('take_profit', signal.get('targets'))
                            entry = signal.get('entry')
                            sl = signal.get('stop_loss')
                            tp = signal.get('take_profit')
                            if entry is not None and sl is not None and tp is not None and abs(entry - sl) > 0:
                                signal['rr_ratio'] = abs(tp - entry) / abs(entry - sl)
                            else:
                                signal['rr_ratio'] = signal.get('rr_ratio', 0)
                            scored_signals_all.append(signal)
                            store_signal(signal)
                except Exception:
                    # Isolate per-asset failures so the loop stays alive.
                    continue

            # Ranking and Dispatch
            ranked_signals = rank_signals(scored_signals_all)
            if DRY_RUN:
                for sig in (ranked_signals.get('vip', []) + ranked_signals.get('premium', [])):
                    print("[DRY RUN]", sig)
            else:
                from db.database import get_all_user_ids

                user_ids = get_all_user_ids()
                for user_id in user_ids:
                    dispatch_signals(ranked_signals, user_id=user_id)
        except Exception:
            # Keep process alive; production version should log structured errors.
            pass

        time.sleep(max(5, cycle_sleep_seconds))
