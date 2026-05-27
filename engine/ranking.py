import os

from engine.ml import score_signal, get_live_strategy_weight


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
        strategy_name = str(signal.get("strategy_name") or signal.get("strategy") or signal.get("name") or "").strip()
        live_weight = get_live_strategy_weight(strategy_name, default=1.0) if strategy_name else 1.0
        weighted_base = base_score * live_weight
        final_score = (0.6 * weighted_base) + (0.4 * ml_score) if ml_prob is not None else weighted_base
        # Persist blended score for downstream consumers
        signal['score_final'] = final_score
        signal['score_ml'] = ml_score if ml_prob is not None else None
        signal['strategy_weight'] = live_weight

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

