

def score_signal(signal):
    """Single-arg scorer used internally by the pipeline.
    
    Weights:
    - Confidence (50%): Base strategy agreement/strength (reject <0.3 base)
    - R/R Ratio (30%): Risk/reward quality (favors 2:1+, penalizes <1.5)
    - Volatility (20%): Lower is better (high volatility penalized)
    - Regime Fit (bonus): +10-20% for alignment with market regime
    - ML Probability (boost): 0.8-1.2x multiplier when available
    
    Target Win Rate Optimization:
    - Enforce good risk/reward (1.5 minimum for edge)
    - Penalize high volatility environments
    - Bonus signals that align with market regime
    - Reject only extremely low-confidence base signals (<0.2)
    """
    # Target: 0..100 score
    confidence = float(signal.get("confidence", 0) or 0)
    confidence = min(max(confidence, 0.0), 1.0)
    
    # ULTRA-STRICT QUALITY GATE: Only trade-worthy setups
    # (Less than 50% base strategy confidence = no edge)
    if confidence < 0.50:
        return 0.0

    entry = signal.get("entry")
    stop = signal.get("stop")
    target = signal.get("targets", entry)
    rr = abs(target - entry) / abs(entry - stop) if entry and stop and abs(entry - stop) > 0 else 0

    rr_component = rr_score(rr)              # 0..1
    vol_component = volatility_quality_score(signal)  # 0..1
    
    # SOFT GATES: Penalize weak signals, don't hard-reject
    # Signals with poor RR or high volatility still score, just lower
    
    # Base score: weighted components
    score = (confidence * 50.0) + (rr_component * 30.0) + (vol_component * 20.0)
    
    # Hard rejection for poor R/R (2.0:1 minimum is table stakes)
    if rr < 2.0:
        return 0.0  # Hard reject: need 2:1 minimum for edge
    
    # REGIME ALIGNMENT BONUS: +10-20% for signals aligned with market regime
    # (Better trades happen when signal aligns with broader trend)
    regime_fit = signal.get("regime_fit") or signal.get("htf_alignment") or 0.5
    try:
        regime_fit = float(regime_fit)
        regime_fit = min(max(regime_fit, 0.0), 1.0)
        regime_bonus = 1.0 + (regime_fit * 0.2)  # 1.0 to 1.2 multiplier
        score = score * regime_bonus
    except Exception:
        pass
    
    # ML PROBABILITY BOOST: 0.8-1.2x multiplier
    # (Trust ML model when it's confident)
    ml_prob = signal.get("ml_probability")
    if ml_prob is not None:
        try:
            ml_val = float(ml_prob)
            ml_val = min(max(ml_val, 0.0), 1.0)
            ml_boost = 0.8 + (ml_val * 0.4)  # Range [0.8, 1.2]
            score = score * ml_boost
        except Exception:
            pass
    
    # EXCEPTIONAL R/R REWARD: Extra bonus for 2.5:1+ (rare high-probability trades)
    if rr >= 2.5:
        score = score * 1.20  # 20% bonus for exceptional R/R
    elif rr >= 2.0:
        score = score * 1.15  # 15% bonus for excellent R/R (2:1+)
    
    return round(min(score, 100.0), 2)  # Cap at 100 to keep scores readable


def calculate_signal_score(signal, risk_profile=None, regime=None):
    """Compatibility wrapper (signal, risk_profile, regime) -> numeric score."""
    return score_signal(signal)


# --- Helper scoring components (lightweight defaults) ---
def strategy_agreement_score(signal):
    return float(signal.get("agreement", 0.5) or 0.5)


def rr_score(rr):
    """Score risk/reward ratio. Higher RR is better (optimal: 2.5:1 to 3:1).
    
    ULTRA-STRICT for win rate recovery:
    - <2.0:1 = 0.0 (reject - need minimum 2:1 edge)
    - 2.0:1 = 0.50 (minimum acceptable)
    - 2.5:1 = 0.75 (good quality setup)
    - 3.0:1 = 1.00 (excellent - ideal setup)
    - >3.0:1 = 1.0 (capped)
    
    Rationale: 16% win rate requires MASSIVE R/R advantage to be profitable
    """
    try:
        rr = float(rr)
    except Exception:
        rr = 0.0
    
    # Hard floor: reject RR < 2.0 (need 2:1 minimum)
    if rr < 2.0:
        return 0.0
    
    # Scale: 2.0 is 50%, 3.0 is 100%
    return float(min(max((rr - 2.0) / 1.0, 0.0), 1.0))


def htf_alignment_score(signal):
    return float(signal.get("htf_alignment", 0.5) or 0.5)


def regime_fit_score(signal, regime=None):
    return float(signal.get("regime_fit", 0.5) or 0.5)


def volatility_quality_score(signal):
    """Score volatility quality (lower volatility = better conditions = higher score).
    
    ULTRA-STRICT for win rate recovery:
    - vol <= 0.08 (8%): score 1.0 (ideal low-volatility)
    - vol = 0.10 (10%): score 0.50 (marginal)
    - vol >= 0.12 (12%): score 0.0 (reject - too volatile for reliable execution)
    
    Rationale: High volatility = poor fills, slippage, stop hunting
    With 16% win rate, we need PERFECT conditions to turn it around
    """
    vol = signal.get("volatility", 0.0)
    try:
        vol = float(vol)
    except Exception:
        vol = 0.0
    
    if vol <= 0.08:
        return 1.0  # Perfect
    elif vol >= 0.12:
        return 0.0  # Hard reject: too volatile
    else:
        # Linear scale: 0.08→0.12 maps to 1.0→0.0
        return float((0.12 - vol) / (0.12 - 0.08))


def historical_winrate_score(signal):
    return float(signal.get("historical_winrate", 0.5) or 0.5)


def liquidity_score(signal):
    return float(signal.get("liquidity", 0.5) or 0.5)
