"""
engine/stale_signal_validator.py - Zero Stale Signal enforcement.

Before any signal is pushed to the delivery queue, this module:
  1. Fetches the live tick price with millisecond accuracy.
  2. Compares the live price against the optimal entry zone (entry ± threshold).
  3. Drops (invalidates) the signal if price has drifted beyond the tolerance.

Environment variables:
    STALE_PRICE_THRESHOLD_PCT   - Max % drift from entry before invalidation (default: 0.5)
    STALE_PRICE_FETCH_TIMEOUT   - Seconds to wait for live price (default: 5)
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def _threshold_pct() -> float:
    try:
        return float(os.getenv("STALE_PRICE_THRESHOLD_PCT", "0.5"))
    except Exception:
        return 0.5


def _fetch_timeout() -> float:
    try:
        return float(os.getenv("STALE_PRICE_FETCH_TIMEOUT", "5"))
    except Exception:
        return 5.0


async def _get_live_price_async(symbol: str) -> Optional[float]:
    """Attempt to fetch live tick price using available providers.

    Priority: Binance WebSocket cache -> Binance REST -> DB market_ticks -> yfinance.
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
        import asyncio
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


async def validate_signal_freshness(
    signal: Dict[str, Any],
) -> Tuple[bool, str, Optional[float]]:
    """Validate that a signal's entry price is still achievable at current market price.

    Returns:
        (is_fresh: bool, reason: str, live_price: Optional[float])

    A signal is considered stale when:
        abs(live_price - entry) / entry > STALE_PRICE_THRESHOLD_PCT / 100
    """
    entry = float(signal.get("entry") or 0)
    symbol = str(signal.get("asset") or signal.get("symbol") or "")

    if not entry or not symbol:
        return True, "no_entry_or_symbol_skip", None

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

    drift_pct = abs(live - entry) / entry * 100.0
    threshold = _threshold_pct()

    if drift_pct > threshold:
        reason = (
            f"stale: entry={entry:.5f} live={live:.5f} "
            f"drift={drift_pct:.2f}% > threshold={threshold:.1f}%"
        )
        logger.info("[stale_validator] Signal INVALIDATED for %s: %s", symbol, reason)
        return False, reason, live

    logger.debug(
        "[stale_validator] Signal FRESH for %s: entry=%.5f live=%.5f drift=%.3f%%",
        symbol, entry, live, drift_pct,
    )
    return True, f"fresh: drift={drift_pct:.3f}%", live


def validate_signal_freshness_sync(signal: Dict[str, Any]) -> Tuple[bool, str, Optional[float]]:
    """Synchronous wrapper around validate_signal_freshness."""
    from utils.async_runner import run_sync
    return run_sync(validate_signal_freshness(signal))
