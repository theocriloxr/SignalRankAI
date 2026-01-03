

def score_signal(signal):
    """Single-arg scorer used internally by the pipeline.
    
    Weights:
    - Confidence (50%): Base strategy agreement/strength
    - R/R Ratio (30%): Risk/reward quality (favors 2:1 or better)
    - Volatility (20%): Lower is better (reduced slippage risk)
    - ML Probability (boost): When available, multiplies final score
    """
    # Target: 0..100 score
    confidence = float(signal.get("confidence", 0) or 0)
    confidence = min(max(confidence, 0.0), 1.0)

    entry = signal.get("entry")
    stop = signal.get("stop")
    target = signal.get("targets", entry)
    rr = abs(target - entry) / abs(entry - stop) if entry and stop and abs(entry - stop) > 0 else 0

    rr_component = rr_score(rr)              # 0..1
    vol_component = volatility_quality_score(signal)  # 0..1

    score = (confidence * 50.0) + (rr_component * 30.0) + (vol_component * 20.0)
    
    # Apply ML probability boost if available
    ml_prob = signal.get("ml_probability")
    if ml_prob is not None:
        try:
            ml_val = float(ml_prob)
            ml_boost = 0.8 + (ml_val * 0.4)  # Range [0.8, 1.2] for [0, 1] ML prob
            score = score * ml_boost
        except Exception:
            pass
    
    # Penalize weak R/R
    if rr < 1.5:
        score = score * 0.7  # 30% penalty for poor risk/reward
    elif rr >= 2.0:
        score = score * 1.15  # 15% bonus for excellent risk/reward (2:1+)
    
    return round(score, 2)


def calculate_signal_score(signal, risk_profile=None, regime=None):
    """Compatibility wrapper (signal, risk_profile, regime) -> numeric score."""
    return score_signal(signal)


# --- Helper scoring components (lightweight defaults) ---
def strategy_agreement_score(signal):
    return float(signal.get("agreement", 0.5) or 0.5)


def rr_score(rr):
    """Score risk/reward ratio. Higher RR is better (up to 3:1 = max score).
    
    Targets:
    - 1.5:1 = 0.50 (acceptable)
    - 2.0:1 = 0.67 (good)
    - 3.0:1 = 1.00 (excellent)
    """
    try:
        rr = float(rr)
    except Exception:
        rr = 0.0
    # More generous: 1.5 is 50%, 3.0 is 100%
    if rr < 1.5:
        return 0.0  # Reject poor RR
    return float(min(max((rr - 1.5) / 1.5, 0.0), 1.0))


def htf_alignment_score(signal):
    return float(signal.get("htf_alignment", 0.5) or 0.5)


def regime_fit_score(signal, regime=None):
    return float(signal.get("regime_fit", 0.5) or 0.5)


def volatility_quality_score(signal):
    vol = signal.get("volatility", 0.0)
    try:
        vol = float(vol)
    except Exception:
        vol = 0.0
    return float(1.0 - min(max(vol, 0.0), 1.0))


def historical_winrate_score(signal):
    return float(signal.get("historical_winrate", 0.5) or 0.5)


def liquidity_score(signal):
    return float(signal.get("liquidity", 0.5) or 0.5)
