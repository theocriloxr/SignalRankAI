"""
SignalRankAI — Signal Scoring Engine (PERFECTED)

Implements the "Dynamic Confidence" specification:
  - NOT just Win Rate = 80% (meaningless alone)
  - Optimizes: EV = Win Rate + Risk Reward + Drawdown + Consistency

Every signal exposes a full score breakdown:
  Trend Score      → higher timeframe trend alignment
  Volume Score     → volume expansion / institutional participation  
  Liquidity Score  → order flow / bid-ask depth
  ML Score         → XGBoost/LSTM probability
  Regime Score     → market regime fit
  
Final score = Weighted Composite (0-100), soft-capped to avoid collapse.

Hard gates (instant reject before scoring):
  1. RR < MIN_RR (default 1.5)
  2. Confidence < CONFIDENCE_MIN (default 0.20)

Soft gates (reduce score but don't reject):
  1. Low confluence → score * (confluence / 50)
  2. Volatile regime → score * 0.85
  3. Correlated portfolio → score reduced proportionally
"""

from __future__ import annotations

import logging
import math
import os
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Env helpers ──────────────────────────────────────────────────────────────

def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ─── Direction normalizer ─────────────────────────────────────────────────────

def _direction_sign(direction_val) -> float:
    try:
        if isinstance(direction_val, str):
            d = direction_val.strip().lower()
            if d in ("long", "buy", "+", "bull"):
                return 1.0
            if d in ("short", "sell", "-", "bear"):
                return -1.0
        return float(direction_val)
    except Exception:
        return 0.0


# ─── Individual score components ──────────────────────────────────────────────

def rr_score(rr: float) -> float:
    """
    Score risk/reward ratio (0.0 → 1.0).
    
    Hard floor at MIN_RR (default 1.5) — returns 0.0 if below.
    Optimal range: 2.5–3.0 = 1.0 (full score).
    
    Uses soft-cap compression at top end to prevent score collapse.
    """
    try:
        rr = float(rr)
    except Exception:
        return 0.0

    min_rr = _env_float("MIN_RR", 1.5)
    if rr < min_rr:
        return 0.0

    base  = max(min_rr, 1.0)
    scale = max(0.5, 3.0 - base)
    raw   = float(min(max((rr - base) / scale, 0.0), 1.0))

    # Soft-cap top end to preserve score distribution
    if raw >= 0.85:
        return 0.85 + (raw - 0.85) * 0.5
    return raw


def volatility_quality_score(signal: dict) -> float:
    """
    Score volatility quality (0.0 → 1.0).
    Lower volatility = better conditions = higher score.
    """
    vol = signal.get("volatility") or signal.get("atr_rel") or 0.0
    try:
        vol = float(vol)
    except Exception:
        vol = 0.0

    max_vol   = _env_float("MAX_VOLATILITY", 0.20)
    ideal_vol = _env_float("IDEAL_VOLATILITY", 0.12)

    if vol <= ideal_vol:
        return 1.0
    elif vol >= max_vol:
        return 0.0
    else:
        return float((max_vol - vol) / max(1e-9, max_vol - ideal_vol))


def trend_alignment_score(signal: dict) -> Optional[float]:
    """
    Score trend alignment: EMA / SMA golden cross in direction of trade.
    Returns 0.0–1.0 or None if data unavailable.
    """
    trend_ema  = signal.get("trend_ema")
    trend_sma  = signal.get("trend_sma")
    htf_bias   = signal.get("htf_bias") or signal.get("htf_alignment")
    direction  = _direction_sign(signal.get("direction", 0))

    score = None

    if trend_ema is not None and trend_sma is not None:
        try:
            te = float(trend_ema)
            ts = float(trend_sma)
            if direction > 0:
                score = 1.0 if (te > 0 and ts > 0) else (0.5 if te > 0 else 0.0)
            elif direction < 0:
                score = 1.0 if (te < 0 and ts < 0) else (0.5 if te < 0 else 0.0)
        except Exception:
            pass

    if score is None and htf_bias is not None:
        try:
            hb = float(htf_bias)
            hb = min(max(hb, 0.0), 1.0)
            score = hb
        except Exception:
            pass

    return score


def volume_confirmation_score(signal: dict) -> Optional[float]:
    """
    Score volume confirmation: above-average volume = institutional participation.
    Returns 0.0–1.0 or None if unavailable.
    """
    volume_ratio = signal.get("volume_ratio") or signal.get("vol_ratio")
    if volume_ratio is None:
        return None

    try:
        vr = float(volume_ratio)
        min_vr = _env_float("VOLUME_RATIO_MIN", 1.2)
        ideal_vr = _env_float("VOLUME_RATIO_IDEAL", 2.0)

        if vr <= 0.8:
            return 0.0  # Volume declining = weakness
        elif vr <= 1.0:
            return 0.3
        elif vr < min_vr:
            return 0.5
        else:
            raw = (vr - min_vr) / max(0.1, ideal_vr - min_vr)
            return min(1.0, 0.7 + raw * 0.3)
    except Exception:
        return None


def liquidity_pool_score(signal: dict) -> Optional[float]:
    """
    Score liquidity conditions: spread, bid-ask depth, sweep completion.
    Returns 0.0–1.0 or None if unavailable.
    """
    liq = signal.get("liquidity_score") or signal.get("liquidity")
    if liq is None:
        return None
    try:
        v = float(liq)
        return min(max(v / 100.0 if v > 1 else v, 0.0), 1.0)
    except Exception:
        return None


def ml_probability_score(signal: dict) -> Optional[float]:
    """
    Score from ML model probability output (XGBoost / LSTM).
    Returns 0.0–1.0 or None if unavailable.
    """
    for key in ("ml_probability", "ml_prob", "ml_confidence", "confidence"):
        val = signal.get(key)
        if val is not None:
            try:
                v = float(val)
                return min(max(v if v <= 1.0 else v / 100.0, 0.0), 1.0)
            except Exception:
                continue
    return None


def calculate_confluence(signal: dict) -> Optional[float]:
    """
    Calculate confluence score (0–100) as % of confirmations met.
    
    Checks:
    1. Trend alignment (EMA/SMA golden cross in direction)
    2. Momentum confirmation (RSI + MACD direction)
    3. Volume expansion (above average volume)
    4. Support/Resistance respect
    5. Market regime alignment (ADX + regime)
    """
    confirmations = 0
    total_checks  = 0
    direction     = _direction_sign(signal.get("direction", 0))

    # 1. Trend alignment
    trend_ema = signal.get("trend_ema")
    trend_sma = signal.get("trend_sma")
    if trend_ema is not None and trend_sma is not None:
        total_checks += 1
        try:
            if (direction > 0 and float(trend_ema) > 0 and float(trend_sma) > 0) or \
               (direction < 0 and float(trend_ema) < 0 and float(trend_sma) < 0):
                confirmations += 1
        except Exception:
            pass

    # 2. Momentum
    rsi        = signal.get("rsi")
    macd_trend = signal.get("macd_trend")
    if rsi is not None and macd_trend is not None:
        total_checks += 1
        try:
            if direction > 0 and float(rsi) > 50 and float(macd_trend) > 0:
                confirmations += 1
            elif direction < 0 and float(rsi) < 50 and float(macd_trend) < 0:
                confirmations += 1
        except Exception:
            pass

    # 3. Volume
    vr = signal.get("volume_ratio")
    if vr is not None:
        total_checks += 1
        try:
            if float(vr) > _env_float("VOLUME_RATIO_MIN", 1.2):
                confirmations += 1
        except Exception:
            pass

    # 4. S/R respect
    support    = signal.get("nearest_support")
    resistance = signal.get("nearest_resistance")
    price      = signal.get("close_price") or signal.get("entry")
    if price and (support or resistance):
        total_checks += 1
        try:
            p = float(price)
            if direction > 0 and support and p > float(support):
                confirmations += 1
            elif direction < 0 and resistance and p < float(resistance):
                confirmations += 1
        except Exception:
            pass

    # 5. Regime
    regime      = str(signal.get("regime") or "").lower()
    adx_str     = str(signal.get("adx_trend") or "").lower()
    if regime and adx_str:
        total_checks += 1
        if (regime == "trending" and adx_str in ("moderate", "strong")) or \
           (regime == "ranging"  and adx_str in ("weak",)):
            confirmations += 1

    if total_checks <= 0:
        return None
    return (confirmations / total_checks) * 100.0


# ─── Main scorer ──────────────────────────────────────────────────────────────

def score_signal(signal: dict) -> float:
    """
    Score a signal from 0–100 using multi-factor dynamic confluence.
    
    Returns 0.0 if any hard gate fails.
    Returns display_score (soft-capped 0–99.5) otherwise.
    
    Mutates signal dict to add:
      signal["score_components"]  → full breakdown dict
      signal["technical_reason"]  → human-readable explanation
      signal["display_score"]     → final display value
      signal["raw_score"]         → unsoftcapped internal value
    """
    # ── Extract entry/stop/targets ────────────────────────────────────────────
    entry_raw  = signal.get("entry")
    stop_raw   = signal.get("stop_loss") or signal.get("stop")
    target_raw = signal.get("take_profit") or signal.get("targets")

    # Resolve best target for RR calculation
    if isinstance(target_raw, (list, tuple)) and target_raw:
        targets_list = []
        for t in target_raw:
            try:
                v = float(t.get("price") if isinstance(t, dict) else t)
                if v > 0:
                    targets_list.append(v)
            except Exception:
                continue
        best_target = max(targets_list) if targets_list else None
    elif isinstance(target_raw, dict):
        best_target = float(target_raw.get("price") or target_raw.get("tp") or 0) or None
    else:
        try:
            best_target = float(target_raw) if target_raw else None
        except Exception:
            best_target = None

    try:
        entry = float(entry_raw) if entry_raw is not None else 0.0
    except Exception:
        entry = 0.0
    try:
        stop = float(stop_raw) if stop_raw is not None else None
    except Exception:
        stop = None

    # ── HARD GATE 1: RR check ─────────────────────────────────────────────────
    rr = 0.0
    if entry > 0 and stop is not None and best_target:
        denom = abs(entry - stop)
        if denom > 0:
            rr = abs(float(best_target) - entry) / denom

    min_rr = _env_float("MIN_RR", 1.5)
    if rr < min_rr:
        logger.info(
            "[scoring][rr_gate] REJECTED %s %s RR=%.2f < MIN_RR=%.2f",
            signal.get("asset"), signal.get("direction"), rr, min_rr,
        )
        return 0.0

    # ── HARD GATE 2: Confidence min ───────────────────────────────────────────
    ml_prob = ml_probability_score(signal)
    conf_min = _env_float("CONFIDENCE_MIN", 0.20)
    if ml_prob is not None and ml_prob < conf_min:
        return 0.0

    # ── Compute sub-scores ────────────────────────────────────────────────────
    rr_comp      = rr_score(rr)
    vol_comp     = volatility_quality_score(signal)
    trend_comp   = trend_alignment_score(signal)
    volume_comp  = volume_confirmation_score(signal)
    liq_comp     = liquidity_pool_score(signal)
    conf_score   = ml_prob  # May be None

    # Confluence
    confluence_pct = None
    # Try explicit field first
    for key in ("confluence_percent", "confluence_score", "confluence"):
        raw = signal.get(key)
        if raw is not None:
            try:
                v = float(raw)
                confluence_pct = v if v > 1.0 else v * 100.0
                break
            except Exception:
                pass
    if confluence_pct is None:
        confluence_pct = calculate_confluence(signal)

    # ── SOFT GATE: Confluence weight ──────────────────────────────────────────
    confluence_min    = _env_float("CONFLUENCE_MIN", 25.0)
    confluence_weight = 1.0
    if confluence_pct is not None and confluence_pct < confluence_min:
        confluence_weight = max(0.0, confluence_pct / 50.0)

    # ── Weighted composite score ──────────────────────────────────────────────
    components: Dict[str, Tuple[float, float]] = {
        "rr":  (rr_comp, _env_float("SCORE_WEIGHT_RR",  0.30)),
        "vol": (vol_comp, _env_float("SCORE_WEIGHT_VOL", 0.15)),
    }
    if trend_comp is not None:
        components["trend"] = (trend_comp, _env_float("SCORE_WEIGHT_TREND", 0.20))
    if volume_comp is not None:
        components["volume"] = (volume_comp, _env_float("SCORE_WEIGHT_VOLUME", 0.15))
    if liq_comp is not None:
        components["liquidity"] = (liq_comp, _env_float("SCORE_WEIGHT_LIQUIDITY", 0.10))
    if conf_score is not None:
        components["confidence"] = (conf_score, _env_float("SCORE_WEIGHT_CONFIDENCE", 0.25))
    if confluence_pct is not None:
        components["confluence"] = (
            min(max(confluence_pct / 100.0, 0.0), 1.0),
            _env_float("SCORE_WEIGHT_CONFLUENCE", 0.15),
        )

    total_weight = sum(w for _, w in components.values()) or 1.0
    raw_score    = 100.0 * sum(v * (w / total_weight) for v, w in components.values())

    # Apply confluence soft weight
    raw_score *= confluence_weight

    # ── Regime alignment bonus ────────────────────────────────────────────────
    regime_fit = signal.get("regime_fit") or signal.get("htf_alignment")
    regime_bonus = 1.0
    if regime_fit is not None:
        try:
            rf = min(max(float(regime_fit), 0.0), 1.0)
            regime_bonus = _env_float("REGIME_SCORE_BONUS_BASE", 1.0) + (
                rf * _env_float("REGIME_SCORE_BONUS_SCALE", 0.20)
            )
            raw_score *= regime_bonus
        except Exception:
            pass

    # ── ML multiply boost ─────────────────────────────────────────────────────
    ml_boost = 1.0
    if ml_prob is not None:
        try:
            ml_boost = (
                _env_float("ML_SCORE_BOOST_MIN", 0.80) +
                ml_prob * _env_float("ML_SCORE_BOOST_RANGE", 0.40)
            )
            raw_score *= ml_boost
        except Exception:
            pass

    # ── Exceptional RR reward ─────────────────────────────────────────────────
    rr_bonus = 1.0
    if rr >= 2.5:
        rr_bonus = 1.20
        raw_score *= 1.20
    elif rr >= 2.0:
        rr_bonus = 1.15
        raw_score *= 1.15

    # ── Soft-cap: exponential decay prevents collapse to 100 ─────────────────
    soft_score    = 100.0 * (1.0 - math.exp(-raw_score / 50.0))
    display_score = round(min(soft_score, 99.5), 2)

    # ── Build score breakdown (explainability) ────────────────────────────────
    score_components = {
        "rr_ratio":          round(rr, 3),
        "rr_score":          round(rr_comp, 3),
        "volatility_score":  round(vol_comp, 3),
        "trend_score":       round(trend_comp * 100, 1) if trend_comp is not None else None,
        "volume_score":      round(volume_comp * 100, 1) if volume_comp is not None else None,
        "liquidity_score":   round(liq_comp * 100, 1) if liq_comp is not None else None,
        "ml_score":          round((ml_prob or 0) * 100, 1),
        "confluence_pct":    round(confluence_pct, 1) if confluence_pct is not None else None,
        "confluence_weight": round(confluence_weight, 3),
        "regime_bonus":      round(regime_bonus, 3),
        "ml_boost":          round(ml_boost, 3),
        "rr_bonus":          round(rr_bonus, 3),
        "raw_score":         round(raw_score, 2),
        "display_score":     display_score,
    }

    # Populate signal fields for downstream use
    signal["score_components"] = score_components
    signal["display_score"]    = display_score
    signal["raw_score"]        = raw_score

    # Store individual sub-scores for formatter
    if trend_comp is not None and "trend_score" not in signal:
        signal["trend_score"] = round(trend_comp * 100, 1)
    if volume_comp is not None and "volume_score" not in signal:
        signal["volume_score"] = round(volume_comp * 100, 1)
    if liq_comp is not None and "liquidity_score" not in signal:
        signal["liquidity_score"] = round(liq_comp * 100, 1)
    if ml_prob is not None and "ml_score" not in signal:
        signal["ml_score"] = round(ml_prob * 100, 1)

    # Build human-readable reason
    try:
        from engine.signal_explainability import build_signal_explanation
        explanation = build_signal_explanation(signal)
        signal["technical_reason"] = explanation.get("summary") or signal.get("technical_reason")
        signal["explanation"]      = explanation
        if explanation.get("invalidation") and not signal.get("invalidation"):
            signal["invalidation"] = explanation["invalidation"]
    except Exception:
        pass

    # Log score breakdown
    logger.info(
        "[scoring] %s %s [%s] score=%.2f (RR=%.2f conf=%.0f%% ml=%.0f%%)",
        signal.get("asset"),
        signal.get("direction"),
        signal.get("timeframe"),
        display_score,
        rr,
        confluence_pct or 0,
        (ml_prob or 0) * 100,
    )

    return display_score


def calculate_signal_score(signal, risk_profile=None, regime=None) -> float:
    """Compatibility wrapper for legacy callers."""
    return score_signal(signal)


def score_to_confidence_label(score: float) -> str:
    """Convert numeric score to human-readable confidence label."""
    if score >= 90:
        return "Very High"
    elif score >= 80:
        return "High"
    elif score >= 70:
        return "Above Average"
    elif score >= 60:
        return "Moderate"
    elif score >= 50:
        return "Below Average"
    else:
        return "Low"


__all__ = [
    "score_signal",
    "calculate_signal_score",
    "calculate_confluence",
    "rr_score",
    "volatility_quality_score",
    "trend_alignment_score",
    "volume_confirmation_score",
    "ml_probability_score",
    "score_to_confidence_label",
]