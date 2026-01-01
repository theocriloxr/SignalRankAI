

def score_signal(signal):
    """Single-arg scorer used internally by the pipeline."""
    score = 0
    score += float(signal.get("confidence", 0) or 0) * 2
    entry = signal.get("entry")
    stop = signal.get("stop")
    target = signal.get("targets", entry)
    rr = abs(target - entry) / abs(entry - stop) if entry and stop and abs(entry - stop) > 0 else 0
    score += min(rr, 3)
    score += (1 - float(signal.get("volatility", 0) or 0)) * 2
    return round(score, 2)


def calculate_signal_score(signal, risk_profile=None, regime=None):
    """Compatibility wrapper (signal, risk_profile, regime) -> numeric score."""
    return score_signal(signal)


# --- Helper scoring components (lightweight defaults) ---
def strategy_agreement_score(signal):
    return float(signal.get("agreement", 0.5) or 0.5)


def rr_score(rr):
    try:
        rr = float(rr)
    except Exception:
        rr = 0.0
    return float(min(max(rr / 3.0, 0.0), 1.0))


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
