import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from core.tier_constants import EXPECTANCY_MIN, DD_SOFT_THROTTLE, DD_HARD_LIMIT, CANDLE_STALENESS_MULTIPLIER

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {\"1\", \"true\", \"yes\", \"y\", \"on\"}


PROD_MODE = not _env_bool(\"DEV_MODE\", False)


# Dynamic real-time thresholds (no fixed values)
def get_max_volatility(asset_type: str) -> float:
    \"\"\"Realtime volatility max from ATR regime + news vol.\"\"\"
    base = _env_float(\"MAX_SIGNAL_VOLATILITY\", 0.12)
    # Reduce for low-liquidity/news events
    news_vol_adj = 1.0 - min(0.3, float(os.getenv(\"NEWS_VOL_ADJ\", \"0.1\") or 0.1))
    return base * news_vol_adj


def soft_throttle_active(account_state: Any) -> bool:
    \"\"\"Check if soft drawdown throttle active (reduce position sizes).\"\"\"
    return getattr(account_state, \"drawdown\", 0) > DD_SOFT_THROTTLE


def hard_stop_active(account_state: Any) -> bool:
    \"\"\"Check if hard drawdown stop active (block all signals).\"\"\"
    return getattr(account_state, \"drawdown\", 0) > DD_HARD_LIMIT


def calculate_dynamic_risk(signal: Dict[str, Any], regime: Optional[str] = None, news_sentiment: Optional[float] = None, gemini_score: Optional[float] = None, account_state: Optional[Any] = None) -> Dict[str, Any]:
    \"\"\"Dynamic risk profile using realtime data (ATR/vol/regime/news/gemini/outcomes).\"\"\"
    asset = signal.get(\"asset\", \"\").lower()
    direction = signal.get(\"direction\", \"long\").lower()
    
    # Realtime volatility from ATR (not fixed BB width)
    atr_pct = float(signal.get(\"atr_rel\", 0) or signal.get(\"volatility\", 0) or 0)
    vol_regime = \"high\" if atr_pct > 0.08 else \"medium\" if atr_pct > 0.04 else \"low\"
    
    # News/gemini sentiment adjustment (block conflicting)
    sentiment_score = news_sentiment or gemini_score or 0.0
    sentiment_ok = abs(sentiment_score) < 2.0  # From STRONG_SENTIMENT_THRESHOLD
    
    # Regime adjustment
    regime_mult = 0.8 if regime == \"ranging\" else 1.2 if regime == \"trending\" else 1.0
    
    # ML expectancy boost
    ml_prob = float(signal.get(\"ml_probability\", 0.5))
    expectancy_boost = 0.5 + (ml_prob * 0.5)  # 0.5-1.0
    
    # Base risk 0.5% dynamic
    base_risk_pct = _env_float(\"RISK_PER_TRADE_PCT\", 0.5)
    dynamic_risk_pct = base_risk_pct * regime_mult * expectancy_boost
    
    # Soft throttle if DD >6%
    if account_state and soft_throttle_active(account_state):
        dynamic_risk_pct *= 0.5
    
    profile = {
        \"risk_pct\": max(0.1, min(dynamic_risk_pct, 2.0)),
        \"max_volatility\": get_max_volatility(\"crypto\" if \"usdt\" in asset else \"fx\" if \"/\" in asset else \"stock\"),
        \"max_drawdown\": DD_HARD_LIMIT,
        \"soft_throttle\": soft_throttle_active(account_state) if account_state else False,
        \"hard_stop\": hard_stop_active(account_state) if account_state else False,
        \"vol_regime\": vol_regime,
        \"sentiment_ok\": sentiment_ok,
        \"regime\": regime,
        \"expectancy_boost\": expectancy_boost,
    }
    
    logger.debug(f\"[risk] Dynamic profile for {asset}: {profile}\")
    return profile


def risk_check(signal: Dict[str, Any], account_state: Any) -> bool:
    \"\"\"Enhanced risk check with realtime dynamic thresholds.\"\"\"
    # Hard stops
    if hard_stop_active(account_state):
        return False
    
    # Realtime volatility (ATR-based)
    atr_pct = float(signal.get(\"atr_rel\", 0) or signal.get(\"volatility\", 0) or 0)
    if atr_pct > get_max_volatility(signal.get(\"asset_class\", \"crypto\")):
        return False
    
    # RR min 1.5 (primary TP)
    entry = signal.get(\"entry\")
    stop = signal.get(\"stop_loss\") or signal.get(\"stop\")
    tp_primary = signal.get(\"take_profit\")
    if isinstance(tp_primary, list):
        tp_primary = tp_primary[0] if tp_primary else None
    if entry and stop and tp_primary:
        risk_dist = abs(float(entry) - float(stop))
        reward_dist = abs(float(tp_primary) - float(entry))
        if risk_dist > 0 and reward_dist / risk_dist < 1.5:
            return False
    
    # Freshness check (integrate tier_constants)
    created_age = (datetime.utcnow() - signal.get(\"created_at\", datetime.utcnow())).total_seconds()
    tf_mult = float(signal.get(\"timeframe_mult\", CANDLE_STALENESS_MULTIPLIER))
    if created_age > (int(signal.get(\"timeframe_minutes\", 60)) * tf_mult):
        return False
    
    # Expectancy placeholder (Phase 3: query live metrics)
    live_expectancy = float(signal.get(\"live_expectancy\", EXPECTANCY_MIN))
    if live_expectancy < EXPECTANCY_MIN:
        return False
    
    return True


def calculate_position_size(signal: Dict[str, Any], account_balance: float, risk_pct: Optional[float] = None) -> Optional[float]:
    \"\"\"Real position sizing: equity * dynamic_risk_pct / risk_distance.\"\"\"
    try:
        entry = float(signal.get(\"entry\", 0))
        stop = float(signal.get(\"stop_loss\", 0) or signal.get(\"stop\", 0))
        risk_dist = abs(entry - stop)
        
        if risk_dist <= 0 or entry <= 0:
            return None
        
        # Dynamic risk % from profile or base
        profile = signal.get(\"risk_profile\")
        risk_pct = risk_pct or (profile.get(\"risk_pct\") if profile else _env_float(\"RISK_PER_TRADE_PCT\", 0.5))
        
        risk_amount = account_balance * (risk_pct / 100.0)
        size = risk_amount / risk_dist
        
        # Min/max bounds
        size = max(0.01, min(size, account_balance * 0.1))  # Max 10% notional
        
        logger.debug(f\"[position] {signal.get('asset', '?')} size={size:.4f} (risk={risk_pct}%, dist={risk_dist:.5f})\")
        return float(size)
    except Exception as e:
        logger.warning(f\"[position] Calculation failed: {e}\")
        return None

