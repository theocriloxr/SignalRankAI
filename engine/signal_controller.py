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

import threading
import time

class SignalController:
    def __init__(self):
        self.min_score = MIN_SCORE_THRESHOLD
        self.kill_switch = False
        self.drawdown_threshold = 0.25  # Example: 25% loss triggers protection
        self.session_map = {
            'London': ['GBP', 'EUR'],
            'New York': ['USD', 'CAD'],
            'Asia': ['JPY', 'AUD', 'NZD']
        }
        self.rate_limit = {}

    def approve_signals(self, strategy_signals, regime):
        if self.kill_switch:
            return []
        # Correlation filter
        filtered = self.correlation_filter(strategy_signals)
        consensus_signals = apply_consensus_filter(filtered)
        approved = []
        for signal in consensus_signals:
            if not self.session_active(signal):
                continue
            risk_profile = calculate_dynamic_risk(signal, regime)
            score = calculate_signal_score(signal, risk_profile, regime)
            if score >= self.min_score:
                signal['score'] = score
                signal['risk_profile'] = risk_profile
                signal['watermark'] = self.generate_watermark(signal)
                store_signal(signal)
                approved.append(signal)
        return approved

    def rank_and_release(self, signals):
        if self.kill_switch:
            return []
        # Drawdown protection
        if self.is_drawdown():
            signals = self.reduce_signals(signals)
        return rank_signals(signals)

    def evaluate_strategies(self):
        stats = get_strategy_stats()
        for strat, stat in stats.items():
            if stat['trades'] >= MIN_TRADES_EVAL:
                winrate = stat['winrate']
                if winrate < MIN_WINRATE_DISABLE:
                    disable_strategy(strat)
                elif winrate < MIN_WINRATE_DEGRADE:
                    update_strategy_weight(strat, degrade=True)

    def send_outcome_update(self, signal_id, outcome, tier):
        # Send TP/SL/invalidated updates
        msg = f"Signal {signal_id}: {outcome}"
        if tier == 'FREE':
            msg = f"Summary: {outcome}"
        # TODO: Send via bot
        pass

    def send_expiry_countdown(self, user_id, days_left):
        # Send expiry countdown message
        msg = f"Your Premium access expires in {days_left} day(s). You'll miss high-confidence setups."
        # TODO: Send via bot
        pass

    def send_trade_invalidation(self, signal_id, tier):
        if tier == 'VIP':
            msg = f"Signal {signal_id} canceled due to market change."
            # TODO: Send via bot
        pass

    def correlation_filter(self, signals):
        # Only allow highest-scoring among correlated assets
        # TODO: Implement actual correlation logic
        return signals

    def kill(self):
        self.kill_switch = True

    def revive(self):
        self.kill_switch = False

    def is_drawdown(self):
        # TODO: Check recent performance
        return False

    def reduce_signals(self, signals):
        # Reduce number/risk of signals
        return signals[:max(1, len(signals)//2)]

    def session_active(self, signal):
        # Only trade FX pairs in active sessions
        # TODO: Implement session check
        return True

    def confidence_explanation(self, signal, tier):
        if tier == 'VIP':
            return "Full breakdown: ..."
        elif tier == 'PREMIUM':
            return "Short explanation: ..."
        return None

    def generate_watermark(self, signal):
        # Invisible identifier for user
        return f"WM{hash(str(signal))%10000}"

    def rate_limited(self, user_id):
        now = time.time()
        last = self.rate_limit.get(user_id, 0)
        if now - last < 2:  # 2 seconds between commands
            return True
        self.rate_limit[user_id] = now
        return False
