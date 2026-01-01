def calculate_dynamic_risk(signal, regime=None):
    """Return a risk profile dict (not position size)."""
    return {
        "risk": 1.0,
        "max_volatility": MAX_VOLATILITY,
        "max_drawdown": MAX_DRAWDOWN,
        "regime": regime,
    }

MAX_VOLATILITY = 0.04
MAX_DRAWDOWN = 0.20

def risk_check(signal, account_state):
    """
    Enforce risk management:
    - Block signals with excessive volatility
    - Block if account drawdown breached
    - Block if risk/reward < 1.5
    """
    if signal.get("volatility", 0) > MAX_VOLATILITY:
        return False
    if getattr(account_state, "drawdown", 0) > MAX_DRAWDOWN:
        return False
    entry = signal.get("entry")
    stop = signal.get("stop")
    target = signal.get("targets", entry)
    if entry is None or stop is None or target is None:
        return False
    rr = abs(target - entry) / abs(entry - stop) if abs(entry - stop) > 0 else 0
    if rr < 1.5:
        return False
    return True

def calculate_position_size(signal, risk):
    # Placeholder: implement position sizing logic
    return 1.0
