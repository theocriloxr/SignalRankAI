"""
Central authority for signal approval and release.
No Telegram logic here. Only signal decision logic.
"""

from engine.consensus import apply_consensus_filter
from engine.risk import calculate_dynamic_risk
from engine.scoring import calculate_signal_score
from engine.ranking import rank_signals
from db.database import store_signal, get_strategy_stats, update_strategy_weight, disable_strategy

MIN_SCORE_THRESHOLD = 75
MIN_WINRATE_DISABLE = 0.40
MIN_WINRATE_DEGRADE = 0.45
MIN_TRADES_EVAL = 30

class SignalController:
    def __init__(self):
        self.min_score = MIN_SCORE_THRESHOLD

    def approve_signals(self, strategy_signals, regime):
        # Consensus filter
        consensus_signals = apply_consensus_filter(strategy_signals)
        approved = []
        for signal in consensus_signals:
            risk_profile = calculate_dynamic_risk(signal, regime)
            score = calculate_signal_score(signal, risk_profile, regime)
            if score >= self.min_score:
                signal['score'] = score
                signal['risk_profile'] = risk_profile
                store_signal(signal)
                approved.append(signal)
        return approved

    def rank_and_release(self, signals):
        # Only release signals that pass ranking
        return rank_signals(signals)

    def evaluate_strategies(self):
        # Weekly performance feedback loop
        stats = get_strategy_stats()
        for strat, stat in stats.items():
            if stat['trades'] >= MIN_TRADES_EVAL:
                winrate = stat['winrate']
                if winrate < MIN_WINRATE_DISABLE:
                    disable_strategy(strat)
                elif winrate < MIN_WINRATE_DEGRADE:
                    update_strategy_weight(strat, degrade=True)
