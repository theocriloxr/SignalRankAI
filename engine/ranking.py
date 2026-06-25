import os

from engine.ml import score_signal, get_live_strategy_weight


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


def rank_signals(signals):
    """Accepts a list of signals and returns a dict with keys 'vip', 'premium', 'free'."""
    # Lowered thresholds to allow more signals through (was VIP=80, Premium=68)
    vip_threshold = _env_float("VIP_SCORE_THRESHOLD", 75)
    premium_threshold = _env_float("PREMIUM_SCORE_THRESHOLD", 60)
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
        signal['score_final'] = round(final_score, 2)
        signal['score_ml'] = round(ml_score, 2) if ml_prob is not None else None
        signal['strategy_weight'] = live_weight
        
        # === FIX PHASE 1: Ensure score breakdown is captured ===
        # Already populated by scoring.py score_signal(), but ensure fallback
        if 'score_raw' not in signal:
            signal['score_raw'] = round(weighted_base, 2)
        if 'score_post_threshold' not in signal:
            signal['score_post_threshold'] = round(final_score, 2)
        
        # Generate detailed score breakdown for logging/telegram
        asset = signal.get('asset', signal.get('symbol', 'UNKNOWN'))
        components = signal.get('score_components', {})
        bonuses = signal.get('bonuses_applied', [])
        
        score_breakdown = []
        # Add individual strategy scores
        for comp_name, comp_val in components.items():
            score_breakdown.append(f"{comp_name.upper()}: {comp_val}")
        
        if score_breakdown:
            signal['score_breakdown_text'] = f"{asset} Score: {', '.join(score_breakdown)}"
        
        # Add raw and normalized totals
        if signal.get('score_raw') is not None:
            signal['score_breakdown_text'] = (signal.get('score_breakdown_text', '') + 
                f" | Raw: {signal['score_raw']}").strip()
        
        signal['score_breakdown_text'] = (signal.get('score_breakdown_text', '') + 
            f" | Normalized: {signal.get('score_post_threshold', final_score):.0f}").strip()

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
