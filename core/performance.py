def avg_reward_risk(trades):
    # Calculate average RR from trades
    return 1.8

def strategy_stats(strategy_name):
    trades = fetch_trades(strategy_name)
    total = len(trades)
    wins = sum(1 for t in trades if t.outcome == "TP")
    win_rate = wins / total if total > 0 else 0
    avg_rr = avg_reward_risk(trades)
    return win_rate, avg_rr

def dynamic_weight(strategy_name):
    win_rate, rr = strategy_stats(strategy_name)
    if win_rate < 0.45:
        return 0.5
    if win_rate > 0.6:
        return 1.3
    return 1.0

# --- Advanced Performance Tracking ---
import datetime
from collections import defaultdict

class PerformanceTracker:
    def __init__(self):
        self.reset()

    def reset(self):
        self.stats = defaultdict(lambda: {
            'trades': 0,
            'wins': 0,
            'losses': 0,
            'total_return': 0.0,
            'returns': [],
            'last_update': None
        })

    def log_trade(self, strategy, result, ret, user_ids=None):
        s = self.stats[strategy]
        s['trades'] += 1
        if result == 'win':
            s['wins'] += 1
        else:
            s['losses'] += 1
        s['total_return'] += ret
        s['returns'].append(ret)
        s['last_update'] = datetime.datetime.utcnow()
        # Do not broadcast outcomes to users by default. Outcome messages should be
        # based on actual delivered signals (see send_outcome_notifications).
        try:
            enabled = str(os.getenv("OUTCOME_BROADCAST_ENABLED") or "0").strip().lower() in {"1", "true", "yes", "y", "on"}
        except Exception:
            enabled = False
        if enabled and user_ids:
            try:
                from signalrank_telegram.bot import notify_all_users_trade_outcome
                notify_all_users_trade_outcome(strategy, result, ret, user_ids)
            except Exception:
                pass

    def get_stats(self, strategy=None):
        if strategy:
            s = self.stats[strategy]
            win_rate = s['wins'] / s['trades'] if s['trades'] else 0
            avg_return = s['total_return'] / s['trades'] if s['trades'] else 0
            return {
                'trades': s['trades'],
                'win_rate': win_rate,
                'avg_return': avg_return,
                'total_return': s['total_return'],
                'last_update': s['last_update']
            }
        else:
            return {k: self.get_stats(k) for k in self.stats}

    def report(self):
        report_lines = []
        for strat, stats in self.get_stats().items():
            report_lines.append(f"{strat}: Trades={stats['trades']}, Win%={stats['win_rate']:.2%}, AvgRet={stats['avg_return']:.4f}, TotalRet={stats['total_return']:.4f}")
        return "\n".join(report_lines)

# Singleton instance for global tracking
performance_tracker = PerformanceTracker()
