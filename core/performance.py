def avg_reward_risk(trades):
    # Calculate average RR from trades
    return 1.8

def strategy_stats(strategy_name):
    """Get strategy performance stats from database.
    
    Returns: (win_rate, avg_rr)
    """
    try:
        # ENGINE import removed; use get_engine_for_event_loop() if needed
        from db.repository import get_strategy_performance
        import asyncio
        
        if ENGINE is None:
            return 0.0, 1.8  # fallback
        
        async def _fetch():
            from db.session import get_session
            async with get_session() as session:
                perf = await get_strategy_performance(session, strategy_name)
                await session.commit()
                return perf
        
        try:
            perf = asyncio.run(_fetch())
            win_rate = float(perf.get('win_rate', 0.0)) if perf else 0.0
            avg_rr = float(perf.get('avg_rr', 1.8)) if perf else 1.8
            return win_rate, avg_rr
        except Exception:
            return 0.0, 1.8
    except Exception:
        return 0.0, 1.8

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
