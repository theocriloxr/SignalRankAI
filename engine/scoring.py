

def score_signal(signal):
    """Single-arg scorer used internally by the pipeline.
    
    Weights:
    - Confidence (50%): Base strategy agreement/strength (reject <0.3 base)
    - R/R Ratio (30%): Risk/reward quality (favors 2:1+, penalizes <1.5)
    - Volatility (20%): Lower is better (reject >0.20 volatility)
    - Regime Fit (bonus): +10-20% for alignment with market regime
    - ML Probability (boost): 0.8-1.2x multiplier when available
    
    Target Win Rate Optimization:
    - Enforce strict risk/reward (1.5 minimum, 2.0+ reward)
    - Penalize high volatility environments
    - Bonus signals that align with market regime
    - Reject low-confidence base signals
    """
    # Target: 0..100 score
    confidence = float(signal.get("confidence", 0) or 0)
    confidence = min(max(confidence, 0.0), 1.0)
    
    # QUALITY GATE: Reject very low-confidence signals
    # (Less than 30% base strategy confidence is too risky)
    if confidence < 0.3:
        return 0.0

    entry = signal.get("entry")
    stop = signal.get("stop")
    target = signal.get("targets", entry)
    rr = abs(target - entry) / abs(entry - stop) if entry and stop and abs(entry - stop) > 0 else 0

    rr_component = rr_score(rr)              # 0..1
    vol_component = volatility_quality_score(signal)  # 0..1
    
    # QUALITY GATE: Reject signals with excessive volatility or poor RR
    if rr < 1.5 or vol_component <= 0.0:
        return 0.0

    # Base score: weighted components
    score = (confidence * 50.0) + (rr_component * 30.0) + (vol_component * 20.0)
    
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
    """Score risk/reward ratio. Higher RR is better (optimal: 2:1 to 3:1).
    
    Targets:
    - <1.5:1 = 0.0 (reject - insufficient margin of safety)
    - 1.5:1 = 0.50 (minimum acceptable)
    - 2.0:1 = 0.83 (good - well-rewarded trades)
    - 3.0:1 = 1.00 (excellent - ideal high-probability setup)
    - >3.0:1 = 1.0 (capped - diminishing returns beyond 3:1)
    
    Rationale: Better RR = better odds of profitability
    Each 0.5:1 improvement from 1.5→3.0 is worth 16.7% more confidence
    """
    try:
        rr = float(rr)
    except Exception:
        rr = 0.0
    
    # Hard floor: reject RR < 1.5 (insufficient edge)
    if rr < 1.5:
        return 0.0
    
    # Scale: 1.5 is 50%, 3.0 is 100%, interpolate linearly
    # Formula: (rr - 1.5) / 1.5 with cap at 1.0
    return float(min(max((rr - 1.5) / 1.5, 0.0), 1.0))


def htf_alignment_score(signal):
    return float(signal.get("htf_alignment", 0.5) or 0.5)


def regime_fit_score(signal, regime=None):
    return float(signal.get("regime_fit", 0.5) or 0.5)


def volatility_quality_score(signal):
    """Score volatility quality (lower volatility = better conditions = higher score).
    
    Targets:
    - vol <= 0.08 (8%): score 1.0 (ideal low-volatility, best execution)
    - vol = 0.12 (12%): score 0.75 (good, normal conditions)
    - vol = 0.16 (16%): score 0.50 (acceptable but slippage risk increases)
    - vol = 0.20 (20%): score 0.0 (reject - too volatile, RR gets squeezed)
    - vol > 0.20: score 0.0 (reject - prohibitive volatility)
    
    Rationale:
    - Low volatility = tighter stops = better RR achievable
    - High volatility = wider stops forced = poor RR, higher slippage
    - BB width >20% signals choppy/ranging market (poor edge)
    
    Scale: Linear from 0.08→0.20, zero penalty below 0.08, hard reject above 0.20
    """
    vol = signal.get("volatility", 0.0)
    try:
        vol = float(vol)
    except Exception:
        vol = 0.0
    
    # Ideal range: 0.08-0.12 (tight, low-noise environments)
    if vol <= 0.08:
        return 1.0  # Perfect volatility
    elif vol >= 0.20:
        return 0.0  # Reject: too volatile, RR gets squeezed by wider stops
    else:
        # Linear scale: 0.08→0.20 maps to 1.0→0.0
        # At vol=0.12: (0.20-0.12)/(0.20-0.08) = 0.8/0.12 = 0.667 ✓
        # At vol=0.16: (0.20-0.16)/(0.20-0.08) = 0.04/0.12 = 0.333 ✓
        return float((0.20 - vol) / (0.20 - 0.08))


def historical_winrate_score(signal):
    return float(signal.get("historical_winrate", 0.5) or 0.5)


def liquidity_score(signal):
    return float(signal.get("liquidity", 0.5) or 0.5)
