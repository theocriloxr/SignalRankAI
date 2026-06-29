import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

import numpy as np
import pandas as pd

from core.tier_constants import EXPECTANCY_MIN, DD_SOFT_THROTTLE, DD_HARD_LIMIT, CANDLE_STALENESS_MULTIPLIER
from engine.signal_metrics import resolve_confidence_ratio, resolve_ml_probability, resolve_score_percent

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
    return raw.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


PROD_MODE = not _env_bool("DEV_MODE", False)


# ============================================================================
# PHASE 3: Asset-Class Risk Sizing
# Implements differentiated ATR multipliers, position sizing, and RR requirements
# based on asset class (crypto vs forex vs stocks) to optimize for each market's
# volatility profile and risk/reward characteristics.
# ============================================================================

# PHASE 3: Asset class detection constants
# Major crypto pairs: ~50 primary trading pairs on centralized exchanges
CRYPTO_PAIRS = {
    "BTCUSD", "BTCUSDT", "BTCUSDC",
    "ETHUSD", "ETHUSDT", "ETHUSDC",
    "SOLUSD", "SOLUSDT",
    "BNBUSD", "BNBUSDT",
    "XRPUSD", "XRPUSDT",
    "ADAUSD", "ADAUSDT",
    "DOGEUSD", "DOGEUSDT",
    "LINKUSD", "LINKUSDT",
    "AVAXUSD", "AVAXUSDT",
    "MATICUSD", "MATICUSDT",
    "OPUSD", "OPUSDT",
    "ARBITRUMUSD", "ARBITRUSDT",
    "LITEUSD", "LITEUSDT",
    "BCHUSD", "BCHUSDT",
    "ETCUSD", "ETCUSDT",
    "XLMUSD", "XLMUSDT",
    "VETUSD", "VETUSDT",
    "ICXUSD", "ICXUSDT",
    "TRXUSD", "TRXUSDT",
    "EOSAUSD", "EOSAUSDT",
    "ATOMUSD", "ATOMUSDT",
    "FTMUSD", "FTMUSDT",
    "UNIUSD", "UNIUSDT",
    "SUSHIUSD", "SUSHIUSDT",
    "CROUSD", "CROUSDT",
    "SNXUSD", "SNXUSDT",
    "GMXUSD", "GMXUSDT",
}

# Major forex pairs: ~20 primary FX crosses
FOREX_PAIRS = {
    "EURUSD", "EUR/USD",
    "GBPUSD", "GBP/USD",
    "USDJPY", "USD/JPY",
    "USDHKD", "USD/HKD",
    "USDCAD", "USD/CAD",
    "USDCHF", "USD/CHF",
    "AUDUSD", "AUD/USD",
    "NZDUSD", "NZD/USD",
    "CADUSD", "CAD/USD",
    "CHFUSD", "CHF/USD",
    "GBPJPY", "GBP/JPY",
    "EURJPY", "EUR/JPY",
    "AUDJPY", "AUD/JPY",
    "NZDJPY", "NZD/JPY",
    "EURGBP", "EUR/GBP",
    "EURCHF", "EUR/CHF",
    "EURCAD", "EUR/CAD",
    "GBPCHF", "GBP/CHF",
    "GBPCAD", "GBP/CAD",
}

# PHASE 3: Asset class risk configuration
# Different asset classes have different volatility profiles and optimal risk/reward ratios.
# Crypto: High volatility → wider stops (2.5x ATR), needs larger targets (4x ATR)
# Forex: Standard volatility → balanced stops (2.0x ATR), standard targets (3x ATR)
# Stock: Lower volatility → tight stops (1.5x ATR), conservative targets (2.5x ATR)
ASSET_CLASS_RISK_CONFIG = {
    "crypto": {
        # Stop Loss: 2.5x ATR - crypto volatility requires wider protective stops to avoid shakeouts
        "atr_multiplier_sl": 2.5,
        # Take Profit: 4.0x ATR - higher TP needed to compensate for wider stops and capture volatility
        "atr_multiplier_tp": 4.0,
        # Max position size: 2% of account per trade - limited due to high volatility
        "max_position_pct": 2.0,
        # Portfolio exposure: Max 10% total crypto allocation - cap concentration risk
        "max_portfolio_exposure": 10,
        # Min RR: 1.5x - accept lower risk/reward due to high move potential (volatility)
        "min_rr": 1.5,
        # Dynamic risk percentage boost for crypto (higher expected volatility compensation)
        "risk_pct_boost": 1.0,  # 1.0x = no boost (baseline)
    },
    "forex": {
        # Stop Loss: 2.0x ATR - moderate volatility, standard institutional stops
        "atr_multiplier_sl": 2.0,
        # Take Profit: 3.0x ATR - balanced TP for standard risk/reward (1:1.5 RR typical)
        "atr_multiplier_tp": 3.0,
        # Max position size: 1% of account per trade - established market standard
        "max_position_pct": 1.0,
        # Portfolio exposure: Max 5% forex allocation
        "max_portfolio_exposure": 5,
        # Min RR: 2.0x - higher RR requirement for lower volatility market
        "min_rr": 2.0,
        # Baseline risk percentage (no boost needed)
        "risk_pct_boost": 1.0,
    },
    "stock": {
        # Stop Loss: 1.5x ATR - stocks less volatile, tight stops improve precision
        "atr_multiplier_sl": 1.5,
        # Take Profit: 2.5x ATR - conservative targets suitable for precision trading
        "atr_multiplier_tp": 2.5,
        # Max position size: 0.5% of account per trade - most conservative due to single-name risk
        "max_position_pct": 0.5,
        # Portfolio exposure: Max 3% stock allocation
        "max_portfolio_exposure": 3,
        # Min RR: 2.5x - highest RR requirement (precision over aggression)
        "min_rr": 2.5,
        # Baseline risk percentage (no boost needed)
        "risk_pct_boost": 1.0,
    },
}


def get_asset_class(symbol: str) -> str:
    """
    Detect asset class from symbol name.
    
    Classification logic:
    1. Check against CRYPTO_PAIRS set → return "crypto"
    2. Check against FOREX_PAIRS set → return "forex"
    3. Default → return "stock"
    
    Args:
        symbol: Trading symbol (e.g., "BTCUSD", "EURUSD", "AAPL")
    
    Returns:
        Asset class string: "crypto", "forex", or "stock"
    
    Example:
        >>> get_asset_class("BTCUSD")
        "crypto"
        >>> get_asset_class("EURUSD")
        "forex"
        >>> get_asset_class("AAPL")
        "stock"
    """
    if not symbol:
        return "stock"
    
    symbol_upper = str(symbol).upper().strip()
    
    # Check crypto pairs first (highest priority - most specific)
    if symbol_upper in CRYPTO_PAIRS:
        logger.debug(f"[asset_class] {symbol_upper} classified as CRYPTO")
        return "crypto"
    
    # Check forex pairs (second priority)
    if symbol_upper in FOREX_PAIRS:
        logger.debug(f"[asset_class] {symbol_upper} classified as FOREX")
        return "forex"
    
    # Default to stock (lowest priority - catch-all)
    logger.debug(f"[asset_class] {symbol_upper} classified as STOCK (default)")
    return "stock"


def get_asset_class_config(asset_class: str) -> Dict[str, Any]:
    """
    Get risk configuration for a specific asset class.
    
    Args:
        asset_class: "crypto", "forex", or "stock"
    
    Returns:
        Dictionary containing ATR multipliers, position sizing limits, RR requirements
    
    Raises:
        ValueError if asset_class is not recognized
    """
    asset_class_lower = str(asset_class or "stock").lower().strip()
    if asset_class_lower not in ASSET_CLASS_RISK_CONFIG:
        logger.warning(f"[asset_class_config] Unknown asset class '{asset_class}', defaulting to 'stock'")
        return ASSET_CLASS_RISK_CONFIG["stock"]
    return ASSET_CLASS_RISK_CONFIG[asset_class_lower]


def calculate_stop_loss_by_asset_class(
    signal: Dict[str, Any],
    market_data: Dict[str, Any],
    asset_class: Optional[str] = None,
) -> Optional[float]:
    """
    Calculate stop loss with asset-class-specific ATR multiplier.
    
    Crypto: 2.5x ATR (volatile markets need wider protection)
    Forex: 2.0x ATR (balanced/standard)
    Stock: 1.5x ATR (less volatile, tighter stops)
    
    Args:
        signal: Signal dict with 'entry', 'direction', etc.
        market_data: Market data dict with 'atr' (absolute ATR value)
        asset_class: "crypto", "forex", or "stock" (auto-detected if None)
    
    Returns:
        Stop loss price (float) or None if calculation fails
    
    Example:
        >>> signal = {"entry": 100, "direction": "long"}
        >>> market_data = {"atr": 2.0}
        >>> calculate_stop_loss_by_asset_class(signal, market_data, "crypto")
        95.0  # 100 - (2.0 * 2.5) = 95.0
    """
    try:
        entry = float(signal.get("entry", 0))
        direction = str(signal.get("direction", "long")).lower().strip()
        atr = float(market_data.get("atr", 0))
        
        if entry <= 0 or atr <= 0:
            logger.warning(f"[SL_calc] Invalid entry={entry} or atr={atr}")
            return None
        
        # Detect asset class if not provided
        if asset_class is None:
            asset_class = get_asset_class(signal.get("asset", ""))
        
        config = get_asset_class_config(asset_class)
        multiplier = config.get("atr_multiplier_sl", 2.0)
        
        # Calculate SL based on direction
        if direction == "long":
            sl = entry - (atr * multiplier)
        else:  # short
            sl = entry + (atr * multiplier)
        
        logger.debug(
            f"[SL_calc] asset_class={asset_class} entry={entry} atr={atr} "
            f"multiplier={multiplier} direction={direction} result_sl={sl}"
        )
        return float(sl)
    
    except Exception as e:
        logger.warning(f"[SL_calc] Exception: {e}")
        return None


def calculate_target_price_by_asset_class(
    signal: Dict[str, Any],
    market_data: Dict[str, Any],
    asset_class: Optional[str] = None,
) -> Optional[float]:
    """
    Calculate take profit with asset-class-specific ATR multiplier.
    
    Crypto: 4.0x ATR (capture larger moves, wider volatility)
    Forex: 3.0x ATR (standard institutional target)
    Stock: 2.5x ATR (conservative, precision-focused)
    
    Args:
        signal: Signal dict with 'entry', 'stop_loss', 'direction'
        market_data: Market data dict with 'atr'
        asset_class: "crypto", "forex", or "stock" (auto-detected if None)
    
    Returns:
        Take profit price (float) or None if calculation fails
    
    Example:
        >>> signal = {"entry": 100, "stop_loss": 95, "direction": "long"}
        >>> market_data = {"atr": 2.0}
        >>> calculate_target_price_by_asset_class(signal, market_data, "crypto")
        108.0  # risk_dist=5, TP=100 + (5 * 1.6) = 108.0
    """
    try:
        entry = float(signal.get("entry", 0))
        stop_loss = float(signal.get("stop_loss", 0))
        direction = str(signal.get("direction", "long")).lower().strip()
        atr = float(market_data.get("atr", 0))
        
        if entry <= 0 or stop_loss <= 0 or atr <= 0:
            logger.warning(f"[TP_calc] Invalid entry={entry}, sl={stop_loss}, or atr={atr}")
            return None
        
        # Detect asset class if not provided
        if asset_class is None:
            asset_class = get_asset_class(signal.get("asset", ""))
        
        config = get_asset_class_config(asset_class)
        tp_multiplier = config.get("atr_multiplier_tp", 3.0)
        
        # Risk distance = distance from entry to SL
        risk_distance = abs(entry - stop_loss)
        
        # Reward distance = risk_distance * (TP_multiplier / SL_multiplier)
        # This maintains consistent RR profile across asset classes
        sl_multiplier = config.get("atr_multiplier_sl", 2.0)
        rr_ratio = tp_multiplier / sl_multiplier if sl_multiplier > 0 else 1.0
        reward_distance = risk_distance * rr_ratio
        
        # Calculate TP based on direction
        if direction == "long":
            tp = entry + reward_distance
        else:  # short
            tp = entry - reward_distance
        
        logger.debug(
            f"[TP_calc] asset_class={asset_class} entry={entry} sl={stop_loss} "
            f"risk_dist={risk_distance} rr_ratio={rr_ratio:.2f} direction={direction} result_tp={tp}"
        )
        return float(tp)
    
    except Exception as e:
        logger.warning(f"[TP_calc] Exception: {e}")
        return None


def calculate_position_size_by_asset_class(
    account_balance: float,
    signal_entry: float,
    signal_sl: float,
    risk_amount: float,
    asset_class: Optional[str] = None,
    current_exposure_pct: float = 0.0,
) -> Optional[float]:
    """
    Calculate position size with asset-class-specific constraints.
    
    Applies:
    1. Base sizing from risk amount / risk distance
    2. Per-trade max position cap (crypto 2%, forex 1%, stock 0.5%)
    3. Portfolio exposure check (crypto 10%, forex 5%, stock 3%)
    
    Args:
        account_balance: Total account equity (float)
        signal_entry: Entry price (float)
        signal_sl: Stop loss price (float)
        risk_amount: Amount to risk on this trade (float, e.g., 0.5% of account)
        asset_class: "crypto", "forex", or "stock"
        current_exposure_pct: Current portfolio exposure in this asset class (%)
    
    Returns:
        Position size in base units (float) or None if invalid
    
    Example:
        >>> # Account: $10k, want to risk $50 (0.5%), entry=100, SL=95
        >>> calculate_position_size_by_asset_class(10000, 100, 95, 50, "crypto")
        10.0  # (50 / 5) = 10 units
    """
    try:
        account_balance = float(account_balance)
        signal_entry = float(signal_entry)
        signal_sl = float(signal_sl)
        risk_amount = float(risk_amount)
        current_exposure_pct = float(current_exposure_pct)
        
        if account_balance <= 0 or signal_entry <= 0:
            logger.warning(f"[PosSize_calc] Invalid account_balance={account_balance} or entry={signal_entry}")
            return None
        
        # Detect asset class if not provided
        if asset_class is None:
            asset_class = "stock"
        
        config = get_asset_class_config(asset_class)
        
        # Step 1: Base position size from risk amount
        risk_distance = abs(signal_entry - signal_sl)
        if risk_distance <= 0:
            logger.warning(f"[PosSize_calc] Invalid risk_distance={risk_distance}")
            return None
        
        position_size = risk_amount / risk_distance
        
        # Step 2: Cap by max position percentage
        max_position_pct = config.get("max_position_pct", 1.0)
        max_position_value = (account_balance * max_position_pct) / 100.0
        max_position_units = max_position_value / signal_entry
        
        if position_size > max_position_units:
            logger.info(
                f"[PosSize_calc] Position capped: {position_size:.4f} → {max_position_units:.4f} units "
                f"(max_pct={max_position_pct}% of ${account_balance})"
            )
            position_size = max_position_units
        
        # Step 3: Check portfolio exposure limit
        max_portfolio_exposure = config.get("max_portfolio_exposure", 5.0)
        position_value_pct = (position_size * signal_entry / account_balance) * 100.0
        total_exposure = current_exposure_pct + position_value_pct
        
        if total_exposure > max_portfolio_exposure:
            # Scale down to stay within exposure limit
            available_exposure = max_portfolio_exposure - current_exposure_pct
            if available_exposure > 0:
                scale_factor = available_exposure / position_value_pct
                position_size *= scale_factor
                logger.info(
                    f"[PosSize_calc] Exposure capped: current={current_exposure_pct:.2f}% "
                    f"+ new={position_value_pct:.2f}% > limit={max_portfolio_exposure}% "
                    f"scaled by {scale_factor:.2f}x to {position_size:.4f} units"
                )
            else:
                logger.warning(
                    f"[PosSize_calc] No exposure available: current={current_exposure_pct:.2f}% "
                    f">= limit={max_portfolio_exposure}%"
                )
                return None
        
        # Apply minimum position size floor
        if position_size < 0.01:
            logger.warning(f"[PosSize_calc] Position size {position_size:.6f} below minimum 0.01")
            return None
        
        logger.debug(
            f"[PosSize_calc] asset_class={asset_class} account={account_balance} "
            f"entry={signal_entry} risk_dist={risk_distance} risk_amount={risk_amount} "
            f"position_size={position_size:.4f} max_pct={max_position_pct}% exposure={total_exposure:.2f}%"
        )
        return float(position_size)
    
    except Exception as e:
        logger.warning(f"[PosSize_calc] Exception: {e}")
        return None


# PHASE 2 FIX: Helper to find best target for direction
def best_target_for_direction(entry, stop, targets, direction):
    """Return the best valid target for given direction based on RR.
    
    For longs: returns the highest TP (best reward)
    For shorts: returns the lowest TP (best reward)
    
    Args:
        entry: Entry price float
        stop: Stop loss price float
        targets: List of target prices (single float or list)
        direction: Trade direction ('long' or 'short')
    
    Returns:
        Best target float or None if no valid targets
    """
    if not targets or entry is None or stop is None:
        return None
    
    try:
        entry = float(entry)
        stop = float(stop)
    except (TypeError, ValueError):
        return None
    
    risk_dist = abs(entry - stop)
    if risk_dist <= 0:
        return None
    
    # Normalize targets to list
    if isinstance(targets, (int, float, str)):
        targets = [targets]
    elif isinstance(targets, dict):
        targets = [targets.get("price") or targets.get("tp") or targets.get("target")]
    
    valid = []
    direction = str(direction or "long").lower().strip()
    
    for t in targets:
        try:
            tp_val = float(t) if not isinstance(t, dict) else float(t.get("price") or t.get("tp") or t.get("target"))
            if tp_val and tp_val > 0:
                rr = abs(tp_val - entry) / risk_dist
                valid.append((rr, tp_val))
        except (TypeError, ValueError):
            continue
    
    if not valid:
        return None
    
    # For longs: highest RR (highest TP)
    # For shorts: highest RR (lowest TP - since price goes down)
    if direction == "long":
        return max(valid, key=lambda x: x[0])[1]
    else:
        return max(valid, key=lambda x: x[0])[1]


# PHASE 2 FIX: RR stats tracking
# Store RR rejection reasons for diagnostics
_risk_stats = {
    "rr_tp1": 0,        # RR using first TP
    "rr_best": 0,        # RR using best TP
    "rr_final": 0,       # RR using final TP (as used in calculation)
    "risk_rejected_rr": 0,
    "risk_rejected_volatility": 0,
    "risk_rejected_news": 0,
    "risk_rejected_correlation": 0,
    "risk_rejected_age": 0,
    "risk_rejected_other": 0,
}


def get_risk_stats() -> dict:
    """Get current risk rejection statistics."""
    return dict(_risk_stats)


def reset_risk_stats() -> None:
    """Reset risk statistics counter."""
    global _risk_stats
    _risk_stats = {
        "rr_tp1": 0,
        "rr_best": 0,
        "rr_final": 0,
        "risk_rejected_rr": 0,
        "risk_rejected_volatility": 0,
        "risk_rejected_news": 0,
        "risk_rejected_correlation": 0,
        "risk_rejected_age": 0,
        "risk_rejected_other": 0,
    }


def _record_rr_stats(rr_key: str) -> None:
    """Record RR-related stat for diagnostics."""
    global _risk_stats
    if rr_key in _risk_stats:
        _risk_stats[rr_key] = _risk_stats.get(rr_key, 0) + 1


# Dynamic real-time thresholds (no fixed values)
def get_max_volatility(asset_type: str) -> float:
    """Realtime volatility max from ATR regime + news vol."""
    base = _env_float("MAX_SIGNAL_VOLATILITY", 0.12)
    # Reduce for low-liquidity/news events
    news_vol_adj = 1.0 - min(0.3, float(os.getenv("NEWS_VOL_ADJ", "0.1") or 0.1))
    return base * news_vol_adj


def soft_throttle_active(account_state: Any) -> bool:
    """Check if soft drawdown throttle active (reduce position sizes)."""
    return getattr(account_state, "drawdown", 0) > DD_SOFT_THROTTLE


def hard_stop_active(account_state: Any) -> bool:
    """Check if hard drawdown stop active (block all signals)."""
    return getattr(account_state, "drawdown", 0) > DD_HARD_LIMIT


def check_correlation_gate(
    new_symbol: str,
    active_positions: list[str] | None,
    price_series_by_symbol: dict[str, list[float]] | None = None,
    max_correlation: float = 0.85,
) -> tuple[bool, str]:
    """Block new entries that are too correlated with existing open positions.

    price_series_by_symbol should map symbols to close-price series of equal-ish length.
    """
    try:
        new_symbol_norm = str(new_symbol or "").upper().strip()
        active_norm = [str(s or "").upper().strip() for s in (active_positions or []) if str(s or "").strip()]
        if not new_symbol_norm or not active_norm:
            return True, "no_correlation_check_needed"

        series_map = {k: v for k, v in (price_series_by_symbol or {}).items() if v}
        if new_symbol_norm not in series_map:
            return True, "missing_price_series"

        new_series = pd.Series(series_map.get(new_symbol_norm, []), dtype="float64").dropna()
        if len(new_series) < 10:
            return True, "insufficient_price_history"

        for existing in active_norm:
            if existing == new_symbol_norm:
                continue
            existing_series = pd.Series(series_map.get(existing, []), dtype="float64").dropna()
            if len(existing_series) < 10:
                continue
            length = min(len(new_series), len(existing_series))
            if length < 10:
                continue
            corr = float(np.corrcoef(new_series.iloc[-length:], existing_series.iloc[-length:])[0, 1])
            if np.isnan(corr):
                continue
            if abs(corr) >= float(max_correlation):
                logger.info(
                    "[risk] Correlation block: %s vs %s corr=%.2f threshold=%.2f",
                    new_symbol_norm,
                    existing,
                    corr,
                    max_correlation,
                )
                return False, f"high correlation with {existing}: {corr:.2f}"
        return True, "ok"
    except Exception as exc:
        logger.debug("[risk] correlation gate failed open: %s", exc)
        return True, "correlation_check_failed_open"


def calculate_dynamic_risk(signal: Dict[str, Any], regime: Optional[str] = None, news_sentiment: Optional[float] = None, gemini_score: Optional[float] = None, account_state: Optional[Any] = None) -> Dict[str, Any]:
    """Dynamic risk profile using realtime data (ATR/vol/regime/news/gemini/outcomes)."""
    asset = signal.get("asset", "").lower()
    direction = signal.get("direction", "long").lower()
    
    # Realtime volatility from ATR (not fixed BB width)
    atr_pct = float(signal.get("atr_rel", 0) or signal.get("volatility", 0) or 0)
    vol_regime = "high" if atr_pct > 0.08 else "medium" if atr_pct > 0.04 else "low"
    
    # News/gemini sentiment adjustment (block conflicting)
    sentiment_score = news_sentiment or gemini_score or 0.0
    sentiment_ok = abs(sentiment_score) < 2.0  # From STRONG_SENTIMENT_THRESHOLD
    
    # Regime adjustment
    regime_mult = 0.8 if regime == "ranging" else 1.2 if regime == "trending" else 1.0
    
    # ML expectancy boost
    ml_prob = resolve_ml_probability(signal)
    if ml_prob is None:
        score_pct = resolve_score_percent(signal)
        if score_pct is not None:
            ml_prob = max(0.0, min(score_pct / 100.0, 1.0))
    if ml_prob is None:
        ml_prob = resolve_confidence_ratio(signal)
    if ml_prob is not None:
        exp_base = _env_float("EXPECTANCY_BOOST_BASE", 0.5)
        exp_range = _env_float("EXPECTANCY_BOOST_RANGE", 0.5)
        expectancy_boost = exp_base + (ml_prob * exp_range)
    else:
        expectancy_boost = 1.0
    
    # Base risk 0.5% dynamic
    base_risk_pct = _env_float("RISK_PER_TRADE_PCT", 0.5)
    dynamic_risk_pct = base_risk_pct * regime_mult * expectancy_boost
    
    # Soft throttle if DD >6%
    if account_state and soft_throttle_active(account_state):
        dynamic_risk_pct *= 0.5
    
    profile = {
        "risk_pct": max(0.1, min(dynamic_risk_pct, 2.0)),
        "max_volatility": get_max_volatility("crypto" if "usdt" in asset else "fx" if "/" in asset else "stock"),
        "max_drawdown": DD_HARD_LIMIT,
        "soft_throttle": soft_throttle_active(account_state) if account_state else False,
        "hard_stop": hard_stop_active(account_state) if account_state else False,
        "vol_regime": vol_regime,
        "sentiment_ok": sentiment_ok,
        "regime": regime,
        "expectancy_boost": expectancy_boost,
    }
    
    logger.debug(f"[risk] Dynamic profile for {asset}: {profile}")
    return profile


def risk_check(signal: Dict[str, Any], account_state: Any) -> bool:
    """Enhanced risk check with realtime dynamic thresholds."""
    # Hard stops
    if hard_stop_active(account_state):
        return False
    
    # Realtime volatility (ATR-based)
    atr_pct = float(signal.get("atr_rel", 0) or signal.get("volatility", 0) or 0)
    if atr_pct > get_max_volatility(signal.get("asset_class", "crypto")):
        return False
    
# ORIGINAL VALUE: 1.5 - Made configurable via MIN_RR_RISK env var (default 1.5)
    # ADDED: diagnostic logging to identify which gate rejects signals
    min_rr_risk = float(os.getenv("MIN_RR_RISK", "1.5") or 1.5)
    entry = signal.get("entry")
    stop = signal.get("stop_loss") or signal.get("stop")
    
    # FIX: Check ALL take profit levels, not just the first one
    # Use the best target that aligns with trade direction
    tp_primary = signal.get("take_profit")
    if isinstance(tp_primary, list):
        # For longs: want highest TP (best reward)
        # For shorts: want lowest TP (best reward)
        direction = str(signal.get("direction") or "long").lower()
        valid_tps = []
        for tp in tp_primary:
            try:
                tp_val = float(tp) if not isinstance(tp, dict) else float(tp.get("price") or tp.get("tp") or tp.get("target"))
                if tp_val and tp_val > 0:
                    valid_tps.append(tp_val)
            except (TypeError, ValueError):
                continue
        
        if valid_tps:
            if direction == "long":
                # Long: take the highest TP for best RR
                tp_primary = max(valid_tps)
            else:
                # Short: take the lowest TP for best RR
                tp_primary = min(valid_tps)
        else:
            tp_primary = None
    elif isinstance(tp_primary, dict):
        tp_primary = tp_primary.get("price") or tp_primary.get("tp") or tp_primary.get("target")
    
    if entry and stop and tp_primary:
        risk_dist = abs(float(entry) - float(stop))
        reward_dist = abs(float(tp_primary) - float(entry))
        rr_ratio = reward_dist / risk_dist if risk_dist > 0 else 0
        if rr_ratio < min_rr_risk:
            # DEBUG: Log detailed RR rejection info
            logger.warning(
                f"[RISK_DEBUG] RR_REJECTED asset={signal.get('asset')} "
                f"rr_ratio={rr_ratio:.4f} min_required={min_rr_risk} "
                f"entry={entry} stop={stop} tp={tp_primary} "
                f"risk_dist={risk_dist:.4f} reward_dist={reward_dist:.4f}"
            )
            return False
    
    # Freshness check (integrate tier_constants)
    created_age = (datetime.utcnow() - signal.get("created_at", datetime.utcnow())).total_seconds()
    tf_mult = float(signal.get("timeframe_mult", CANDLE_STALENESS_MULTIPLIER))
    if created_age > (int(signal.get("timeframe_minutes", 60)) * tf_mult):
        return False
    
    # Expectancy gate is optional. Default behavior is down-weight-first in
    # scoring, with hard blocking only when explicitly enabled.
    live_expectancy = float(signal.get("live_expectancy", EXPECTANCY_MIN))
    if _env_bool("EXPECTANCY_HARD_BLOCK_ENABLED", False) and live_expectancy < EXPECTANCY_MIN:
        return False

    # Correlation gate: block when new trade is too correlated with existing open positions.
    if _env_bool("ENABLE_CORRELATION_GATE", True):
        try:
            active_positions = signal.get("active_positions") or []
            price_series_by_symbol = signal.get("correlation_prices") or {}
            if not price_series_by_symbol and active_positions:
                try:
                    from utils.async_runner import run_sync
                    from data.market_data import fetch_market_data_cached

                    timeframe = str(signal.get("timeframe") or "1h").lower().strip()
                    symbols = [str(signal.get("asset") or signal.get("symbol") or "").upper().strip()] + [
                        str(sym or "").upper().strip() for sym in active_positions
                    ]
                    series_map: dict[str, list[float]] = {}
                    for sym in symbols:
                        if not sym:
                            continue
                        md = run_sync(fetch_market_data_cached(sym, [timeframe]), timeout=20.0)
                        candles = (md or {}).get(timeframe, {}).get("candles", []) if isinstance(md, dict) else []
                        closes = []
                        for candle in candles or []:
                            try:
                                closes.append(float(candle.get("close")))
                            except Exception:
                                continue
                        if closes:
                            series_map[sym] = closes
                    price_series_by_symbol = series_map
                except Exception:
                    price_series_by_symbol = {}
            ok, _reason = check_correlation_gate(
                str(signal.get("asset") or signal.get("symbol") or ""),
                list(active_positions) if isinstance(active_positions, (list, tuple, set)) else [],
                price_series_by_symbol if isinstance(price_series_by_symbol, dict) else {},
                max_correlation=float(os.getenv("MAX_PORTFOLIO_CORRELATION", "0.85") or 0.85),
            )
            if not ok:
                return False
        except Exception:
            pass
    
    return True


def calculate_position_size(signal: Dict[str, Any], account_balance: float, risk_pct: Optional[float] = None) -> Optional[float]:
    """
    Real position sizing: equity * dynamic_risk_pct / risk_distance.
    
    PHASE 3: Now asset-class-aware - applies differentiated position caps and
    portfolio exposure limits based on asset class (crypto/forex/stock).
    """
    try:
        entry = float(signal.get("entry", 0))
        stop = float(signal.get("stop_loss", 0) or signal.get("stop", 0))
        risk_dist = abs(entry - stop)
        
        if risk_dist <= 0 or entry <= 0:
            return None
        
        # Dynamic risk % from profile or base
        profile = signal.get("risk_profile")
        risk_pct = risk_pct or (profile.get("risk_pct") if profile else _env_float("RISK_PER_TRADE_PCT", 0.5))
        
        risk_amount = account_balance * (risk_pct / 100.0)
        
        # Keep the legacy public sizing contract by default: risk amount divided
        # by risk distance. The asset-class cap path is available for live
        # deployments that explicitly opt in via env or per-signal metadata.
        asset_class = signal.get("asset_class") or get_asset_class(signal.get("asset", ""))
        current_exposure = signal.get("current_exposure_pct", 0.0)
        enforce_asset_caps = str(
            signal.get("enforce_asset_caps", os.getenv("POSITION_SIZE_ENFORCE_ASSET_CAPS", "0"))
        ).strip().lower() in {"1", "true", "yes", "on"}

        if not enforce_asset_caps:
            size = risk_amount / risk_dist
            logger.debug(
                f"[position] {signal.get('asset', '?')} basic size={size:.4f} "
                f"(risk={risk_pct}%, dist={risk_dist:.5f})"
            )
            return float(size)
        
        size = calculate_position_size_by_asset_class(
            account_balance=account_balance,
            signal_entry=entry,
            signal_sl=stop,
            risk_amount=risk_amount,
            asset_class=asset_class,
            current_exposure_pct=current_exposure,
        )
        
        if size is None:
            # Fallback to basic sizing if asset-class calculation fails
            size = risk_amount / risk_dist
            size = max(0.01, min(size, account_balance * 0.1))  # Max 10% notional
            logger.debug(f"[position] {signal.get('asset', '?')} FALLBACK size={size:.4f} (risk={risk_pct}%, dist={risk_dist:.5f})")
            return float(size)
        
        logger.debug(f"[position] {signal.get('asset', '?')} asset_class={asset_class} size={size:.4f} (risk={risk_pct}%, dist={risk_dist:.5f})")
        return float(size)
    except Exception as e:
        logger.warning(f"[position] Calculation failed: {e}")
        return None
