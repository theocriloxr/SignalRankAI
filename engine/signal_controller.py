# --- CENTRALIZED SIGNAL CONTROLLER ---
from engine.consensus import apply_consensus_filter
from engine.risk import calculate_dynamic_risk
from engine.scoring import calculate_signal_score
from engine.ranking import rank_signals
from db.database import store_signal, get_strategy_stats, update_strategy_weight, disable_strategy
import time

MIN_SCORE_THRESHOLD = 75
MIN_WINRATE_DISABLE = 0.40
MIN_WINRATE_DEGRADE = 0.45
MIN_TRADES_EVAL = 30

class SignalController:
    def __init__(self):
        self.min_score = MIN_SCORE_THRESHOLD
        self.kill_switch = False
        self.drawdown_threshold = 0.25  # Example: 25% loss triggers protection
        self.correlation_groups = {
            'BTC': ['ETH', 'BNB', 'LTC'],
            'NASDAQ': ['SPX', 'DOW'],
            # Add more as needed
        }
        self.rate_limit = {}
        # Setup audit logger
        import logging
        self.audit_logger = logging.getLogger('audit')
        self.audit_logger.setLevel(logging.INFO)
        fh = logging.FileHandler('audit.log')
        fh.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        if not self.audit_logger.hasHandlers():
            self.audit_logger.addHandler(fh)

        # Global kill-switch state
        self.KILL_SWITCH = {'enabled': False, 'reason': ''}

    def enable_kill_switch(self, reason, admin_id=None):
        self.KILL_SWITCH['enabled'] = True
        self.KILL_SWITCH['reason'] = reason
        self.audit_logger.warning(f"KILL SWITCH ENABLED by {admin_id}: {reason}")

    def disable_kill_switch(self, admin_id=None):
        self.KILL_SWITCH['enabled'] = False
        self.KILL_SWITCH['reason'] = ''
        self.audit_logger.info(f"KILL SWITCH DISABLED by {admin_id}")

    def is_kill_switch_enabled(self):
        return self.KILL_SWITCH['enabled']

    def log_audit_event(self, event, user_id=None, details=None):
        msg = f"EVENT: {event}"
        if user_id:
            msg += f" | user_id={user_id}"
        if details:
            msg += f" | details={details}"
        self.audit_logger.info(msg)

    def approve_signals(self, strategy_signals, regime):
        if self.kill_switch:
            return []
        deduped = self.deduplicate_signals(strategy_signals)
        capped = self.cap_correlation(deduped)
        consensus_signals = apply_consensus_filter(capped)
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

    def deduplicate_signals(self, signals):
        # Remove duplicate signals by asset, direction, and timeframe
        seen = set()
        deduped = []
        for s in signals:
            key = (s['asset'], s['direction'], s.get('timeframe'))
            if key not in seen:
                deduped.append(s)
                seen.add(key)
        return deduped

    def cap_correlation(self, signals):
        # Only allow one signal per correlated group (highest score)
        group_map = {}
        for s in signals:
            group = None
            for k, v in self.correlation_groups.items():
                if s['asset'] in v or s['asset'] == k:
                    group = k
                    break
            if group:
                if group not in group_map or s.get('score', 0) > group_map[group].get('score', 0):
                    group_map[group] = s
            else:
                group_map[s['asset']] = s
        return list(group_map.values())

    def rank_and_release(self, signals):
        if self.kill_switch:
            return {'vip': [], 'premium': [], 'free': []}
        if self.is_drawdown():
            self.kill_switch = True
            # Optionally notify owner here
            return {'vip': [], 'premium': [], 'free': []}
        return rank_signals(signals)

    def is_drawdown(self):
        # TODO: Implement drawdown logic using live stats
        # Example: return True if drawdown exceeds threshold
        return False

    def generate_watermark(self, signal):
        return f"WM{hash(str(signal))%10000}"

    def session_active(self, signal):
        # Only trade FX pairs in active sessions (stub)
        return True
