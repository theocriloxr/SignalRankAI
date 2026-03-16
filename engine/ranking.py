import os

from engine.ml import score_signal


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


def rank_signals(signals):
    """Accepts a list of signals and returns a dict with keys 'vip', 'premium', 'free'."""
    vip_threshold = _env_float("VIP_SCORE_THRESHOLD", 80)
    premium_threshold = _env_float("PREMIUM_SCORE_THRESHOLD", 68)
    premium = []
    vip = []
    free = []
    for signal in signals:
        base_score = float(signal.get('score', 0) or 0)
        ml_prob = score_signal(signal)
        ml_score = (ml_prob or 0.0) * 100.0
        final_score = (0.6 * base_score) + (0.4 * ml_score) if ml_prob is not None else base_score
        # Persist blended score for downstream consumers
        signal['score_final'] = final_score
        signal['score_ml'] = ml_score if ml_prob is not None else None

        if final_score >= vip_threshold:
            vip.append(signal)
        elif final_score >= premium_threshold:
            premium.append(signal)
        else:
            free.append(signal)

    vip.sort(key=lambda x: x.get('score_final', x.get('score', 0)), reverse=True)
    premium.sort(key=lambda x: x.get('score_final', x.get('score', 0)), reverse=True)
    free.sort(key=lambda x: x.get('score_final', x.get('score', 0)), reverse=True)
    return {'vip': vip, 'premium': premium, 'free': free}

