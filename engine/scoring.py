
def score_signal(signal):
    """
    Honest heuristic scoring:
    - confidence
    - risk/reward
    - volatility
    """
    score = 0
    score += signal.get("confidence", 0) * 2
    entry = signal.get("entry")
    stop = signal.get("stop")
    target = signal.get("targets", entry)
    rr = abs(target - entry) / abs(entry - stop) if entry and stop and abs(entry - stop) > 0 else 0
    score += min(rr, 3)
    score += (1 - signal.get("volatility", 0)) * 2
    return round(score, 2)
