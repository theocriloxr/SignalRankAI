import os
import logging
import math
from typing import Dict, Any, Optional
from datetime import datetime

from utils.timeutils import now_utc_naive, to_naive_utc

import numpy as np
import pandas as pd

from core.tier_constants import EXPECTANCY_MIN, DD_SOFT_THROTTLE, DD_HARD_LIMIT, CANDLE_STALENESS_MULTIPLIER
from engine.risk_advice import account_drawdown, bounded_risk_percent, bounded_spot_units, finite_number

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
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


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
    "BTCUSD",
    "BTCUSDT",
    "BTCUSDC",
    "ETHUSD",
    "ETHUSDT",
    "ETHUSDC",
    "SOLUSD",
    "SOLUSDT",
    "BNBUSD",
    "BNBUSDT",
    "XRPUSD",
    "XRPUSDT",
    "ADAUSD",
    "ADAUSDT",
    "DOGEUSD",
    "DOGEUSDT",
    "LINKUSD",
    "LINKUSDT",
    "AVAXUSD",
    "AVAXUSDT",
    "MATICUSD",
    "MATICUSDT",
    "OPUSD",
    "OPUSDT",
    "ARBITRUMUSD",
    "ARBITRUSDT",
    "LITEUSD",
    "LITEUSDT",
    "BCHUSD",
    "BCHUSDT",
    "ETCUSD",
    "ETCUSDT",
    "XLMUSD",
    "XLMUSDT",
    "VETUSD",
    "VETUSDT",
    "ICXUSD",
    "ICXUSDT",
    "TRXUSD",
    "TRXUSDT",
    "EOSAUSD",
    "EOSAUSDT",
    "ATOMUSD",
    "ATOMUSDT",
    "FTMUSD",
    "FTMUSDT",
    "UNIUSD",
    "UNIUSDT",
    "SUSHIUSD",
    "SUSHIUSDT",
    "CROUSD",
    "CROUSDT",
    "SNXUSD",
    "SNXUSDT",
    "GMXUSD",
    "GMXUSDT",
}

# Major forex pairs: ~20 primary FX crosses
FOREX_PAIRS = {
    "EURUSD",
    "EUR/USD",
    "GBPUSD",
    "GBP/USD",
    "USDJPY",
    "USD/JPY",
    "USDHKD",
    "USD/HKD",
    "USDCAD",
    "USD/CAD",
    "USDCHF",
    "USD/CHF",
    "AUDUSD",
    "AUD/USD",
    "NZDUSD",
    "NZD/USD",
    "CADUSD",
    "CAD/USD",
    "CHFUSD",
    "CHF/USD",
    "GBPJPY",
    "GBP/JPY",
    "EURJPY",
    "EUR/JPY",
    "AUDJPY",
    "AUD/JPY",
    "NZDJPY",
    "NZD/JPY",
    "EURGBP",
    "EUR/GBP",
    "EURCHF",
    "EUR/CHF",
    "EURCAD",
    "EUR/CAD",
    "GBPCHF",
    "GBP/CHF",
    "GBPCAD",
    "GBP/CAD",
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
    "index": {
        # Index CFDs/futures move quickly around session opens and macro events.
        "atr_multiplier_sl": 1.7,
        "atr_multiplier_tp": 3.0,
        "max_position_pct": 0.5,
        "max_portfolio_exposure": 3,
        "min_rr": 2.0,
        "risk_pct_boost": 0.8,
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
    clean_symbol = symbol_upper.replace("/", "").replace("_", "").replace("-", "")

    # Check crypto pairs first (highest priority - most specific)
    if symbol_upper in CRYPTO_PAIRS:
        logger.debug(f"[asset_class] {symbol_upper} classified as CRYPTO")
        return "crypto"

    # Check forex pairs (second priority)
    if symbol_upper in FOREX_PAIRS:
        logger.debug(f"[asset_class] {symbol_upper} classified as FOREX")
        return "forex"

    try:
        from data.fetcher import is_index

        if is_index(symbol_upper):
            logger.debug(f"[asset_class] {symbol_upper} classified as INDEX")
            return "index"
    except Exception:
        index_symbols = {
            "US500",
            "SP500",
            "SPX",
            "GSPC",
            "US100",
            "NAS100",
            "NDX",
            "US30",
            "DJI",
            "DOW",
            "GER40",
            "DAX",
            "UK100",
            "JPN225",
            "JP225",
            "VIX",
            "HK50",
            "FRA40",
            "EU50",
            "AUS200",
        }
        if symbol_upper.startswith("^") or clean_symbol in index_symbols:
            logger.debug(f"[asset_class] {symbol_upper} classified as INDEX")
            return "index"

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
    """Spot-unit advice constrained by both class notional and loss budgets."""
    equity, entry, stop, loss, exposure = (finite_number(value) for value in
        (account_balance, signal_entry, signal_sl, risk_amount, current_exposure_pct))
    if any(value is None for value in (equity, entry, stop, loss, exposure)):
        return None
    assert equity is not None and entry is not None and stop is not None and loss is not None and exposure is not None
    if min(equity, entry, stop) <= 0 or loss < 0 or not 0 <= exposure <= 100:
        return None
    name = str(asset_class or "stock").lower().strip()
    if name not in ASSET_CLASS_RISK_CONFIG:
        return None
    config = ASSET_CLASS_RISK_CONFIG[name]
    position_pct, portfolio_pct = finite_number(config.get("max_position_pct")), finite_number(config.get("max_portfolio_exposure"))
    if position_pct is None or portfolio_pct is None or not 0 <= position_pct <= 100 or not 0 <= portfolio_pct <= 100:
        return None
    available_pct = min(position_pct, max(0.0, portfolio_pct - exposure))
    if loss == 0 or available_pct == 0:
        return 0.0
    units = bounded_spot_units(equity=equity, entry=entry, stop=stop, risk_amount=loss,
                               notional_budget=equity * available_pct / 100)
    return units if units > 0 else None


# PHASE 2 FIX: Helper to find best target for direction
def best_target_for_direction(entry, stop, targets, direction):
    """Select a finite target on the profitable side of valid stop geometry."""
    entry, stop = finite_number(entry), finite_number(stop)
    side = str(direction or "long").lower().strip()
    if entry is None or stop is None or min(entry, stop) <= 0:
        return None
    if ((side in {"long", "buy"} and stop >= entry)
            or (side in {"short", "sell"} and stop <= entry)
            or side not in {"long", "buy", "short", "sell"}):
        return None
    if isinstance(targets, (int, float, str, dict)):
        targets = [targets]
    if not isinstance(targets, (list, tuple)):
        return None
    valid = []
    for target in targets:
        raw = target.get("price") or target.get("tp") or target.get("target") if isinstance(target, dict) else target
        value = finite_number(raw)
        if value is None or value <= 0:
            continue
        if (side in {"long", "buy"} and value > entry) or (side in {"short", "sell"} and value < entry):
            valid.append(value)
    return (max(valid) if side in {"long", "buy"} else min(valid)) if valid else None


# PHASE 2 FIX: RR stats tracking
# Store RR rejection reasons for diagnostics
_risk_stats = {
    "rr_tp1": 0,  # RR using first TP
    "rr_best": 0,  # RR using best TP
    "rr_final": 0,  # RR using final TP (as used in calculation)
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
    """Configured volatility ceiling; invalid policy cannot increase it."""
    base = finite_number(os.getenv("MAX_SIGNAL_VOLATILITY", "0.12"))
    adjustment = finite_number(os.getenv("NEWS_VOL_ADJ", "0.1"))
    if base is None or adjustment is None or not 0 <= base <= 1 or not 0 <= adjustment <= 1:
        return 0.0
    return base * (1.0 - min(0.3, adjustment))


def soft_throttle_active(account_state: Any) -> bool:
    """Check validated account drawdown, accepting mappings and objects."""
    drawdown = account_drawdown(account_state)
    return drawdown is not None and drawdown > DD_SOFT_THROTTLE


def hard_stop_active(account_state: Any) -> bool:
    """An invalid account state or reached hard limit blocks execution."""
    drawdown = account_drawdown(account_state)
    return drawdown is None or drawdown >= DD_HARD_LIMIT


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


def calculate_dynamic_risk(
    signal: Dict[str, Any],
    regime: Optional[str] = None,
    news_sentiment: Optional[float] = None,
    gemini_score: Optional[float] = None,
    account_state: Optional[Any] = None,
) -> Dict[str, Any]:
    """Bounded advice using qualified calibration; no heuristic probability."""
    advice_signal = dict(signal)
    if regime is not None:
        advice_signal["regime"] = regime
    if news_sentiment is not None:
        advice_signal["news_sentiment"] = news_sentiment
    elif gemini_score is not None:
        advice_signal["gemini_score"] = gemini_score
    atr_value = signal.get("atr_rel") if signal.get("atr_rel") is not None else signal.get("volatility", 0)
    atr_pct = finite_number(atr_value)
    sentiment = finite_number(advice_signal.get("news_sentiment") if advice_signal.get("news_sentiment") is not None else advice_signal.get("gemini_score", 0))
    risk_pct = bounded_risk_percent(advice_signal, base=os.getenv("RISK_PER_TRADE_PCT", "0.5"),
        probability_base=os.getenv("EXPECTANCY_BOOST_BASE", "0.5"),
        probability_range=os.getenv("EXPECTANCY_BOOST_RANGE", "0.5"), account_state=account_state)
    maximum_volatility = get_max_volatility(str(signal.get("asset_class") or get_asset_class(str(signal.get("asset") or ""))))
    if atr_pct is None or atr_pct < 0 or maximum_volatility <= 0 or atr_pct > maximum_volatility:
        risk_pct = 0.0
    return {
        "risk_pct": risk_pct,
        "max_volatility": maximum_volatility,
        "max_drawdown": DD_HARD_LIMIT,
        "soft_throttle": soft_throttle_active(account_state) if account_state is not None else False,
        "hard_stop": hard_stop_active(account_state) if account_state is not None else False,
        "vol_regime": "unavailable" if atr_pct is None else "high" if atr_pct > 0.08 else "medium" if atr_pct > 0.04 else "low",
        "sentiment_ok": sentiment is not None and abs(sentiment) < 2.0,
        "regime": advice_signal.get("regime"),
        "expectancy_boost": 1.0,  # Retained response field; expectancy grants no capital boost.
        "broker_contract_certified": False,
    }


def risk_check(signal: Dict[str, Any], account_state: Any) -> bool:
    """Enhanced risk check with realtime dynamic thresholds."""
    # Hard stops
    if hard_stop_active(account_state):
        return False

    atr_raw = signal.get("atr_rel") if signal.get("atr_rel") is not None else signal.get("volatility", 0)
    atr_pct = finite_number(atr_raw)
    maximum_volatility = get_max_volatility(str(signal.get("asset_class") or "crypto"))
    if atr_pct is None or atr_pct < 0 or maximum_volatility <= 0 or atr_pct > maximum_volatility:
        return False
    minimum_rr = finite_number(os.getenv("MIN_RR_RISK", "1.5"))
    entry = finite_number(signal.get("entry"))
    stop = finite_number(signal.get("stop_loss") if signal.get("stop_loss") is not None else signal.get("stop"))
    target = best_target_for_direction(entry, stop, signal.get("take_profit"), signal.get("direction"))
    if minimum_rr is None or minimum_rr <= 0 or entry is None or stop is None or target is None:
        return False
    ratio = abs(target - entry) / abs(entry - stop)
    if finite_number(ratio) is None or ratio < minimum_rr:
        return False

    # Generation-time callers may not have stamped creation yet. Supplied
    # timestamps must be plausible and the bar budget is converted to seconds.
    now = now_utc_naive()
    created_at = signal.get("created_at")
    if not isinstance(created_at, datetime):
        created_at = now
    created_at = to_naive_utc(created_at) or now
    age_seconds = (now - created_at).total_seconds()
    multiplier = finite_number(signal.get("timeframe_mult", CANDLE_STALENESS_MULTIPLIER))
    minutes = finite_number(signal.get("timeframe_minutes", 60))
    if multiplier is None or minutes is None or min(multiplier, minutes) <= 0:
        return False
    freshness_seconds = minutes * 60 * multiplier
    if not math.isfinite(freshness_seconds) or age_seconds < -5 or age_seconds > freshness_seconds:
        return False
    expectancy = finite_number(signal["live_expectancy"]) if "live_expectancy" in signal else None
    if "live_expectancy" in signal and expectancy is None:
        return False
    if _env_bool("EXPECTANCY_HARD_BLOCK_ENABLED", False) and (expectancy is None or expectancy < EXPECTANCY_MIN):
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


def calculate_position_size(
    signal: Dict[str, Any], account_balance: float, risk_pct: Optional[float] = None
) -> Optional[float]:
    """Bounded spot-unit advice; invalid class caps cannot fall back to more risk."""
    equity, entry = finite_number(account_balance), finite_number(signal.get("entry"))
    stop_value = signal.get("stop_loss") if signal.get("stop_loss") is not None else signal.get("stop")
    stop = finite_number(stop_value)
    if equity is None or entry is None or stop is None or min(equity, entry, stop) <= 0:
        return None
    profile = signal.get("risk_profile")
    if profile is not None and not isinstance(profile, dict):
        return None
    if profile is not None and "hard_stop" in profile and not isinstance(profile["hard_stop"], bool):
        return None
    if profile is not None and profile.get("hard_stop") is True:
        return 0.0
    raw_risk = risk_pct if risk_pct is not None else profile["risk_pct"] if profile is not None and "risk_pct" in profile else os.getenv("RISK_PER_TRADE_PCT", "0.5")
    percentage = finite_number(raw_risk)
    if percentage is None or not 0 <= percentage <= 1.25:
        return None
    if percentage == 0:
        return 0.0
    loss = equity * percentage / 100
    units = bounded_spot_units(equity=equity, entry=entry, stop=stop, risk_amount=loss,
        notional_budget=equity * 0.1, direction=signal.get("direction"))
    if units <= 0:
        return None
    enforce_caps = str(signal.get("enforce_asset_caps", os.getenv("POSITION_SIZE_ENFORCE_ASSET_CAPS", "0"))).strip().lower() in {"1", "true", "yes", "on"}
    if enforce_caps:
        capped = calculate_position_size_by_asset_class(equity, entry, stop, loss,
            signal.get("asset_class") or get_asset_class(str(signal.get("asset") or "")),
            signal.get("current_exposure_pct", 0.0))
        if capped is None:
            return None
        units = min(units, capped)
    return units
