import os


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


def calculate_dynamic_risk(signal, regime=None):
    """Return a risk profile dict (not position size)."""
    return {
        "risk": 1.0,
        "max_volatility": MAX_VOLATILITY,
        "max_drawdown": MAX_DRAWDOWN,
        "regime": regime,
    }

# Strategies currently use Bollinger band width (fraction of price) as volatility.
# A default 0.04 was too strict and effectively blocked most signals.
MAX_VOLATILITY = _env_float("MAX_SIGNAL_VOLATILITY", 0.20)
MAX_DRAWDOWN = _env_float("MAX_ACCOUNT_DRAWDOWN", 0.20)

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
    # Basic position sizing logic (risk-per-trade)
    return 1.0
