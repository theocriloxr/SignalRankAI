def rank_signals(signals):
    """Accepts a list of signals and returns a dict with keys 'vip', 'premium', 'free'."""
    premium = []
    vip = []
    free = []
    for signal in signals:
        if signal.get('score', 0) >= 85:
            vip.append(signal)
        elif signal.get('score', 0) >= 75:
            premium.append(signal)
        else:
            free.append(signal)
    vip.sort(key=lambda x: x.get('score', 0), reverse=True)
    premium.sort(key=lambda x: x.get('score', 0), reverse=True)
    free.sort(key=lambda x: x.get('score', 0), reverse=True)
    return {'vip': vip, 'premium': premium, 'free': free}

from db.database import get_unreleased_signals
