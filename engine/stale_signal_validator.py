"""
engine/stale_signal_validator.py - Zero Stale Signal enforcement with Advanced Features.

Before any signal is pushed to the delivery queue, this module:
  1. Fetches the live tick price with millisecond accuracy.
  2. Compares the live price against the optimal entry zone (entry ± threshold).
  3. Drops (invalidates) the signal if price has drifted beyond the tolerance.

Advanced Features (Version 2.0):
  - ATR-based dynamic drift thresholds (adapts to market volatility)
  - Entry zone logic (range instead of exact price)
  - Ghost price detection with sanity check
  - Secondary source validation

Environment variables:
    STALE_PRICE_THRESHOLD_PCT   - Override % drift threshold for ALL asset classes.
    STALE_PRICE_FETCH_TIMEOUT   - Seconds to wait for live price (default: 5)
    USE_DYNAMIC_DRIFT          - Enable ATR-based dynamic thresholds (default: true)
    GHOST_PRICE_CHECK        - Enable ghost price detection (default: true)
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class StaleSignalValidator:
    """
    StaleSignalValidator - Validates signal freshness against live market prices.
    
    CRITICAL FIX: This class now explicitly reads from environment variables during __init__
    to prevent the "Zero Threshold" bug (threshold stuck at 0.0%).
    
    The validator ensures that:
    1. Signal entry prices are still achievable at current market prices
    2. Price drift doesn't exceed the configured threshold
    3. Entry zone logic allows for legitimate price fluctuations
    """
    
    def __init__(self):
        """
        Initialize the validator with environment-based configuration.
        
        CRITICAL: Force the code to read the Railway Env Var, or default to a SAFE 1.5%
        This fixes the "Zero Threshold" bug where the threshold was stuck at 0.0%.
        
        FIX: Increased default from 1.0% to 1.5% to handle crypto volatility.
        The old 0.2% caused constant invalidation during volatile moves.
        """
        # Force the code to read the Railway Env Var, or default to a SAFE 1.5%
        # This explicit reading prevents the 0.0% threshold bug
        raw_threshold = os.getenv("STALE_PRICE_THRESHOLD_PCT", "1.5")
        try:
            self.default_threshold = float(raw_threshold) / 100.0
        except (ValueError, TypeError):
            self.default_threshold = 0.015  # 1.5% safe fallback
        
        # Safety net: NEVER allow 0.0 threshold - always use minimum 0.5%
        if self.default_threshold <= 0.0:
            self.default_threshold = 0.005  # 0.5% minimum
        
        logger.info(
            f"[StaleSignalValidator] Initialized with threshold={self.default_threshold*100:.2f}% "
            f"(from env: STALE_PRICE_THRESHOLD_PCT={raw_threshold})"
        )
    
    def get_threshold(self) -> float:
        """Return the default threshold as a percentage (0-1 range)."""
        return self.default_threshold
    
    def validate(self, signal_price: float, live_price: float) -> bool:
        """
        Validate that the signal price is still fresh compared to live price.
        
        Args:
            signal_price: The original signal's entry price
            live_price: Current live market price
        
        Returns:
            True if the signal is still fresh (drift within threshold)
            False if the signal is stale (drift exceeds threshold)
        """
        if signal_price <= 0 or live_price <= 0:
            return True  # Can't validate, assume OK

        drift = abs(signal_price - live_price) / signal_price

        if drift > self.default_threshold:
            logger.info(
                f"[StaleSignalValidator] Signal INVALIDATED: drift={drift*100:.2f}% > "
                f"threshold={self.default_threshold*100:.2f}%"
            )
            return False
        return True


# Global instance - ensures env vars are read once at import time
_validator = StaleSignalValidator()

# Asset-class defaults when STALE_PRICE_THRESHOLD_PCT is not set.
# FIX: Increased crypto threshold from 3.5% to 2.5% and commodity from 1.0% to 1.5%
# This fixes signal starvation after risk_passed (17 signals passing but final_signals=0)
_CLASS_THRESHOLDS: dict[str, float] = {
    "crypto":     2.5,   # 2.5% (was 3.5% - lowered to allow more signals through)
    "stock":      0.5,   # 0.5% (stocks)
    "commodity":  1.5,   # 1.5% (was 1.0% - Gold/Silver need more room)
    "fx":         0.8,   # 0.8% / ~80 pips (increased for realistic FX latency)
}


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


def _detect_asset_class(symbol: str) -> str:
    """Identify asset class from the symbol string."""
    sym = symbol.upper()
    # Crypto: ends with USDT / USDC / BTC / ETH / BNB suffix
    if sym.endswith(("USDT", "USDC", "BTC", "ETH", "BNB")):
        return "crypto"
    # FX: standard 6-char currency pairs or contains a slash
    if "/" in sym or (len(sym) == 6 and sym.isalpha()):
        return "fx"
    # Commodities: common tickers
    if sym in {"XAUUSD", "XAGUSD", "WTIUSD", "BRENTUSD", "XAUEUR",
               "GOLD", "SILVER", "OIL", "CRUDE"}:
        return "commodity"
    return "stock"


def get_dynamic_threshold(symbol: str, atr_value: float = 0.0, price: float = 0.0) -> float:
    """
    Calculate ATR-based dynamic drift threshold.
    
    If ATR is provided and USE_DYNAMIC_DRIFT is enabled, the threshold is calculated
    as 10% of ATR (allows for normal market fluctuations).
    
    Args:
        symbol: Trading symbol
        atr_value: Current ATR value (if available)
        price: Current price
    
    Returns:
        Dynamic drift threshold as percentage
    """
    use_dynamic = _env_bool("USE_DYNAMIC_DRIFT", True)
    
    if use_dynamic and atr_value > 0 and price > 0:
        # 10% of ATR as threshold
        # e.g., BTC at $60,000 with $500 ATR = 0.083%
        dynamic_threshold = (atr_value * 0.10) / price
        # Clamp between 0.2% and 5%
        return max(0.002, min(dynamic_threshold, 0.05))
    
    # Fallback to static thresholds
    return _threshold_pct(symbol)


def _threshold_pct(symbol: str = "") -> float:
    """Return the drift tolerance (%) for the given symbol.

    If STALE_PRICE_THRESHOLD_PCT is set explicitly it overrides all classes.
    Otherwise the per-class default is used (see _CLASS_THRESHOLDS).
    
    CRITICAL: Hardcoded fallback to prevent 0.0% threshold bug.
    """
    # CRITICAL FIX: Add safety fallback to prevent 0.0% threshold
    # This prevents the "drift=0.24% > threshold=0.0%" fatal error
    try:
        override = os.getenv("STALE_PRICE_THRESHOLD_PCT", "")
        if override.strip():
            val = float(override.strip())
            if val > 0.0:
                return max(0.01, val)
    except Exception:
        pass
    
    asset_class = _detect_asset_class(symbol) if symbol else "crypto"
    threshold = _CLASS_THRESHOLDS.get(asset_class, 2.0)
    
    # Safety net: NEVER return 0.0 - use minimum 0.5%
    if threshold <= 0.0:
        threshold = 0.5
        
    return threshold


def _fetch_timeout() -> float:
    try:
        return float(os.getenv("STALE_PRICE_FETCH_TIMEOUT", "5"))
    except Exception:
        return 5.0


def is_price_sane(primary_price: float, secondary_price: float, max_diff_pct: float = 1.0) -> bool:
    """
    Check if prices from two sources are aligned (Ghost Price Detection).
    
    If sources differ by more than max_diff_pct%, it's a "Ghost Price".
    
    Args:
        primary_price: Price from primary source
        secondary_price: Price from secondary source  
        max_diff_pct: Maximum allowed difference (default 1%)
    
    Returns:
        True if prices are aligned, False if ghost price detected
    """
    if primary_price <= 0 or secondary_price <= 0:
        return True  # Can't validate, assume OK
    
    diff = abs(primary_price - secondary_price) / primary_price * 100.0
    
    if diff > max_diff_pct:
        logger.critical(
            f"[stale_validator] SENSORS MISALIGNED: Primary={primary_price:.5f}, "
            f"Secondary={secondary_price:.5f}, Diff={diff:.2f}%"
        )
        return False
    
    return True


async def _get_secondary_price(symbol: str) -> Optional[float]:
    """Fetch price from secondary source for ghost price check."""
    # Try CryptoCompare as secondary if primary was Binance
    try:
        import httpx
        url = f"https://min-api.cryptocompare.com/data/price?fsym={symbol.replace('USDT', '')}&tsyms=USD"
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(url)
            if r.status_code == 200:
                data = r.json()
                price = float(data.get("USD", 0) or 0)
                if price > 0:
                    return price
    except Exception:
        pass
    
    return None


async def _get_live_price_async(symbol: str) -> Optional[float]:
    """Attempt to fetch live tick price using available providers.

    Priority: Binance REST -> DB market_ticks -> yfinance.
    Returns None if all providers fail within timeout.
    """
    # 1. Try Binance REST (fastest for crypto)
    try:
        import httpx
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol.upper()}"
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(url)
            if r.status_code == 200:
                data = r.json()
                price = float(data.get("price", 0) or 0)
                if price > 0:
                    return price
    except Exception:
        pass

    # 2. Try DB market_ticks (populated by WS ingest)
    try:
        from db.session import get_session
        from sqlalchemy import text
        async with get_session() as session:
            row = await session.execute(
                text("SELECT price FROM market_ticks WHERE symbol = :sym"),
                {"sym": symbol.upper()},
            )
            r = row.fetchone()
            if r and r[0]:
                return float(r[0])
    except Exception:
        pass

    # 3. yfinance fallback (sync, run in thread)
    try:
        from services.asset_mapper import map_symbol
        yf_sym = map_symbol(symbol, "yfinance") or symbol

        def _yf_price():
            import yfinance as yf
            ticker = yf.Ticker(yf_sym)
            info = ticker.fast_info
            return float(getattr(info, "last_price", None) or 0)

        price = await asyncio.to_thread(_yf_price)
        if price and price > 0:
            return price
    except Exception:
        pass

    return None


def calculate_entry_zone(entry_price: float, atr_value: float = 0.0, direction: str = "long") -> dict:
    """
    Calculate entry zone instead of exact entry price.
    
    Uses ATR to create a "safe zone" where the signal is still valid.
    This allows for legitimate price fluctuations while maintaining risk.
    
    Args:
        entry_price: Original entry price
        atr_value: Current ATR (optional, for dynamic zone sizing)
        direction: "long" or "short"
    
    Returns:
        Dict with 'entry', 'low', 'high' keys
    """
    if atr_value > 0:
        # Zone = 50% of ATR (allows 0.5 ATR movement either way)
        zone = atr_value * 0.5
    else:
        # Fallback: 0.2% of entry price
        zone = entry_price * 0.002
    
    if direction.lower() == "long":
        return {
            "entry": entry_price,
            "low": entry_price - zone,
            "high": entry_price + zone
        }
    else:  # short
        return {
            "entry": entry_price,
            "low": entry_price - zone,
            "high": entry_price + zone
        }


def is_in_entry_zone(entry_price: float, live_price: float, atr_value: float = 0.0, direction: str = "long") -> bool:
    """Check if live price is within the valid entry zone."""
    zone = calculate_entry_zone(entry_price, atr_value, direction)
    return zone["low"] <= live_price <= zone["high"]


async def validate_signal_freshness(
    signal: Dict[str, Any],
    cached_live_price: Optional[float] = None,
) -> Tuple[bool, str, Optional[float]]:
    """Validate that a signal's entry price is still achievable at current market price.

    Args:
        signal: Signal dict containing at least 'entry' and 'asset'/'symbol'.
        cached_live_price: Pre-fetched live price. When provided the network
            fetch is skipped entirely, making batch validation O(1) per signal
            instead of O(1 HTTP round-trip) per signal.

    Returns:
        (is_fresh: bool, reason: str, live_price: Optional[float])

    A signal is considered stale when:
        abs(live_price - entry) / entry > threshold_pct / 100
    where threshold_pct is asset-class-aware, or ATR-based when available.
    """
    entry = float(signal.get("entry") or 0)
    symbol = str(signal.get("asset") or signal.get("symbol") or "")
    atr_value = float(signal.get("atr") or 0)
    direction = str(signal.get("direction") or "long").lower()

    if not entry or not symbol:
        return True, "no_entry_or_symbol_skip", None

    # Use the pre-fetched price when available (avoids redundant HTTP call).
    if cached_live_price is not None and float(cached_live_price) > 0:
        live = float(cached_live_price)
    else:
        try:
            live = await asyncio.wait_for(
                _get_live_price_async(symbol),
                timeout=_fetch_timeout(),
            )
        except asyncio.TimeoutError:
            logger.warning("[stale_validator] Timeout fetching price for %s — allowing signal", symbol)
            return True, "price_fetch_timeout_skip", None
        except Exception as exc:
            logger.warning("[stale_validator] Error fetching price for %s: %s — allowing signal", symbol, exc)
            return True, f"price_fetch_error_skip:{exc}", None

    if live is None:
        logger.debug("[stale_validator] No price available for %s — allowing signal", symbol)
        return True, "price_unavailable_skip", None

    # Ghost price detection using secondary source
    use_ghost_check = _env_bool("GHOST_PRICE_CHECK", True)
    if use_ghost_check:
        secondary_price = await _get_secondary_price(symbol)
        if secondary_price and secondary_price > 0:
            if not is_price_sane(live, secondary_price, max_diff_pct=1.0):
                # Try entry zone logic before invalidating
                if is_in_entry_zone(entry, live, atr_value, direction):
                    logger.info(
                        f"[stale_validator] Ghost price detected but in entry zone: "
                        f"{symbol} entry={entry:.5f} live={live:.5f}"
                    )
                else:
                    reason = (
                        f"ghost_price: primary={live:.5f} secondary={secondary_price:.5f} "
                        f"diff > 1%"
                    )
                    logger.warning(f"[stale_validator] Signal INVALIDATED for {symbol}: {reason}")
                    return False, reason, live

    # Calculate threshold (dynamic ATR-based or static)
    # CRITICAL FIX: Ensure threshold is in percentage form to match drift_pct
    threshold = get_dynamic_threshold(symbol, atr_value, live)
    
    # If threshold is < 1.0, assume it's in decimal form (0.01 = 1%) and convert to percentage
    if threshold < 1.0:
        threshold = threshold * 100.0

# Check drift percentage
    drift_pct = abs(live - entry) / entry * 100.0

    if drift_pct > threshold:
        # Check if we're in the entry zone before final rejection
        if is_in_entry_zone(entry, live, atr_value, direction):
            logger.info(
                f"[stale_validator] Drift {drift_pct:.2f}% exceeds {threshold:.1f}% "
                f"but in entry zone for {symbol} — allowing signal"
            )
            # FIX: Add STALE_AUDIT logging for accepted signals via entry zone
            logger.warning(
                f"[STALE_AUDIT] ACCEPTED %s entry=%.5f live=%.5f diff=%.2f%% threshold=%.2f%% zone_entry",
                symbol, entry, live, drift_pct, threshold
            )
        else:
            reason = (
                f"stale: entry={entry:.5f} live={live:.5f} "
                f"drift={drift_pct:.2f}% > threshold={threshold:.1f}%"
            )
            logger.info("[stale_validator] Signal INVALIDATED for %s: %s", symbol, reason)
            # FIX: Add STALE_AUDIT logging for rejected signals
            logger.warning(
                f"[STALE_AUDIT] REJECTED %s entry=%.5f live=%.5f diff=%.2f%% threshold=%.2f%% reason=stale",
                symbol, entry, live, drift_pct, threshold
            )
            return False, reason, live

    logger.debug(
        "[stale_validator] Signal FRESH for %s: entry=%.5f live=%.5f drift=%.3f%% threshold=%.3f%%",
        symbol, entry, live, drift_pct, threshold,
    )
    # FIX: Add STALE_AUDIT logging for fresh signals
    logger.warning(
        f"[STALE_AUDIT] ACCEPTED {symbol} entry={entry:.5f} live={live:.5f} diff={drift_pct:.2f}% threshold={threshold:.2f}%"
    )
    return True, f"fresh: drift={drift_pct:.3f}%", live


def validate_signal_freshness_sync(signal: Dict[str, Any]) -> Tuple[bool, str, Optional[float]]:
    """Synchronous wrapper around validate_signal_freshness."""
    from utils.async_runner import run_sync
    return run_sync(validate_signal_freshness(signal))


def get_validator() -> StaleSignalValidator:
    """
    Get the global StaleSignalValidator instance.
    
    This function ensures that the validator is properly initialized with
    environment variables and can be used throughout the codebase.
    
    Returns:
        StaleSignalValidator: The global validator instance
    """
    return _validator


def get_threshold_from_env(symbol: str = "") -> float:
    """
    Get the threshold percentage for a given symbol.
    
    This function now uses the global StaleSignalValidator instance to ensure
    consistent threshold values are used throughout the codebase.
    
    Args:
        symbol: Trading symbol (optional, for asset-class detection)
    
    Returns:
        Threshold as a percentage (0-1 range)
    """
    # First try to get from global validator (uses env var)
    global_threshold = _validator.get_threshold()
    
    # If dynamic drift is enabled and we have ATR, use that
    use_dynamic = _env_bool("USE_DYNAMIC_DRIFT", True)
    if use_dynamic:
        # For symbol-based dynamic threshold, we need ATR value
        # This is just the global threshold if no ATR is provided
        return global_threshold
    
    # Fallback to asset-class threshold if no env var is set
    if not os.getenv("STALE_PRICE_THRESHOLD_PCT"):
        return _threshold_pct(symbol) / 100.0
    
    return global_threshold
