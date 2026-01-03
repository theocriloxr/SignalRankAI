import os


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


def rank_signals(signals):
    """Accepts a list of signals and returns a dict with keys 'vip', 'premium', 'free'."""
    vip_threshold = _env_float("VIP_SCORE_THRESHOLD", 72)
    premium_threshold = _env_float("PREMIUM_SCORE_THRESHOLD", 60)
    premium = []
    vip = []
    free = []
    for signal in signals:
        if float(signal.get('score', 0) or 0) >= vip_threshold:
            vip.append(signal)
        elif float(signal.get('score', 0) or 0) >= premium_threshold:
            premium.append(signal)
        else:
            free.append(signal)
    vip.sort(key=lambda x: x.get('score', 0), reverse=True)
    premium.sort(key=lambda x: x.get('score', 0), reverse=True)
    free.sort(key=lambda x: x.get('score', 0), reverse=True)
    return {'vip': vip, 'premium': premium, 'free': free}

