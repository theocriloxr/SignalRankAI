def fetch_trades(strategy_name):
    # Implement DB fetch for trades by strategy
    return []

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
