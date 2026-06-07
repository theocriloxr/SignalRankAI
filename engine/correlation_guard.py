"""
Dynamic Portfolio Correlation Guard: Real-Time Price Correlation Prevention

This module prevents portfolio blow-ups due to over-correlation by mathematically 
calculating the Pearson correlation between price histories of open positions.

The Concept:
- If your bot opens longs on BTC, ETH, SOL, DOT, and AVAX simultaneously
- You don't have 4 different trades — you have 1 giant trade on the entire crypto market
- If Bitcoin drops, ALL 4 hit Stop Loss instantly

The Fix:
- Calculate real-time price correlation between candidate and existing open trades
- If correlation >= threshold (e.g., 85%), VETO the trade
- Must have diverse, non-correlated positions for true portfolio protection

Usage:
    from engine.correlation_guard import CorrelationManager
    
    manager = CorrelationManager(max_correlation=0.85)
    is_allowed = await manager.is_trade_allowed(
        candidate_asset="SOLUSDT",
        open_trades=[...],
        price_history_dict={...}
    )
"""

import logging
from typing import Dict, List, Any, Optional, Set, Tuple
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

logger = logging.getLogger("CorrelationGuard")

# Configuration
DEFAULT_MAX_CORRELATION = float(os.getenv("CORRELATION_GUARD_MAX", "0.85"))
DEFAULT_MIN_HISTORY_POINTS = int(os.getenv("CORRELATION_GUARD_MIN_POINTS", "20"))
DEFAULT_LOOKBACK_HOURS = int(os.getenv("CORRELATION_GUARD_LOOKBACK_HOURS", "24"))


class CorrelationManager:
    """
    Dynamic correlation guard that prevents over-correlation in the portfolio.
    
    Key Logic:
    1. Fetch price history for candidate asset
    2. Fetch price histories of all open trades
    3. Calculate Pearson correlation between candidate and each open trade
    4. If any correlation >= threshold, VETO the trade
    """
    
    def __init__(
        self,
        max_correlation: float = DEFAULT_MAX_CORRELATION,
        min_history_points: int = DEFAULT_MIN_HISTORY_POINTS,
        lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
        enabled: bool = True,
    ):
        self.max_correlation = max_correlation
        self.min_history_points = min_history_points
        self.lookback_hours = lookback_hours
        self.enabled = enabled
        
        # Cache for price histories
        self._price_cache: Dict[str, pd.DataFrame] = {}
        self._cache_ttl_seconds = 180  # 3 minutes
    
    def _fetch_price_history(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Fetch price history for a symbol.
        
        Returns:
            DataFrame with 'close' column, or None on failure
        """
        try:
            from data.providers import fetch_candles_waterfall
            
            # Fetch candles (prefer higher timeframes for cleaner signals)
            for tf in ["1h", "15m", "5m"]:
                candles = fetch_candles_waterfall(symbol, tf, limit=100)
                if candles and len(candles) >= self.min_history_points:
                    break
            
            if not candles or len(candles) < self.min_history_points:
                logger.debug(f"[CorrelationGuard] Insufficient data for {symbol}")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(candles)
            df = df.rename(columns={
                "c": "close", "o": "open", "h": "high", "l": "low", "v": "volume"
            })
            
            # Ensure we have close prices
            if "close" not in df.columns:
                logger.debug(f"[CorrelationGuard] No close column for {symbol}")
                return None
            
            # Convert to numeric and drop NaN
            df["close"] = pd.to_numeric(df["close"], errors="coerce")
            df = df.dropna(subset=["close"])
            
            if len(df) < self.min_history_points:
                logger.debug(f"[CorrelationGuard] Insufficient closes for {symbol}: {len(df)}")
                return None
            
            return df[["close"]]
            
        except ImportError:
            logger.debug(f"[CorrelationGuard] Import error fetching {symbol}")
            return None
        except Exception as e:
            logger.debug(f"[CorrelationGuard] Failed to fetch {symbol}: {e}")
            return None
    
    async def get_price_history(self, symbol: str, use_cache: bool = True) -> Optional[pd.DataFrame]:
        """
        Get price history with optional caching.
        """
        if use_cache:
            cached = self._price_cache.get(symbol)
            if cached is not None:
                return cached
        
        df = self._fetch_price_history(symbol)
        
        if df is not None and use_cache:
            self._price_cache[symbol] = df
        
        return df
    
    def calculate_correlation(
        self,
        prices1: pd.Series,
        prices2: pd.Series,
    ) -> float:
        """
        Calculate Pearson correlation between two price series.
        
        Returns:
            Correlation coefficient (-1 to 1), or 0 on failure
        """
        try:
            # Align by index (timestamp)
            if isinstance(prices1, pd.Series) and isinstance(prices2, pd.Series):
                # Create aligned DataFrame
                df = pd.DataFrame({
                    "p1": prices1,
                    "p2": prices2,
                }).dropna()
                
                if len(df) < 5:
                    return 0.0
                
                corr = df.corr().iloc[0, 1]
                
                if pd.isna(corr):
                    return 0.0
                
                return float(corr)
            
            # Fallback: convert to arrays
            arr1 = np.array(prices1)
            arr2 = np.array(prices2)
            
            min_len = min(len(arr1), len(arr2))
            if min_len < 5:
                return 0.0
            
            arr1 = arr1[:min_len]
            arr2 = arr2[:min_len]
            
            corr_matrix = np.corrcoef(arr1, arr2)
            corr = corr_matrix[0, 1]
            
            if np.isnan(corr):
                return 0.0
            
            return float(corr)
            
        except Exception as e:
            logger.debug(f"[CorrelationGuard] Correlation calc failed: {e}")
            return 0.0
    
    async def is_trade_allowed(
        self,
        candidate_asset: str,
        open_trades: List[Dict[str, Any]],
        price_history_dict: Optional[Dict[str, pd.DataFrame]] = None,
    ) -> Tuple[bool, str]:
        """
        Check if candidate is too correlated with existing open trades.
        
        Args:
            candidate_asset: Symbol being considered for trade
            open_trades: List of active trade dicts with 'asset' field
            price_history_dict: Optional pre-fetched price histories
            
        Returns:
            Tuple of (is_allowed: bool, reason: str)
        """
        if not self.enabled:
            return True, "disabled"
        
        if not open_trades:
            return True, "no_open_trades"
        
        try:
            # Normalize candidate
            cand_symbol = str(candidate_asset or "").upper().strip()
            if not cand_symbol:
                return False, "invalid_candidate"
            
            # Get candidate price history
            if price_history_dict and cand_symbol in price_history_dict:
                cand_prices = price_history_dict[cand_symbol]
            else:
                cand_prices = await self.get_price_history(cand_symbol)
            
            if cand_prices is None or cand_prices.empty:
                logger.debug(f"[CorrelationGuard] No price data for {cand_symbol}, allowing")
                return True, "no_price_data"
            
            # Store existing symbols we've already checked
            checked_assets: Set[str] = set()
            max_corr = 0.0
            max_corr_asset = ""
            
            # Check against each open trade
            for trade in open_trades:
                open_asset = str(trade.get("asset") or trade.get("symbol") or "").upper().strip()
                
                if not open_asset or open_asset == cand_symbol:
                    continue
                
                if open_asset in checked_assets:
                    continue
                
                checked_assets.add(open_asset)
                
                # Get open trade price history
                if price_history_dict and open_asset in price_history_dict:
                    open_prices = price_history_dict[open_asset]
                else:
                    open_prices = await self.get_price_history(open_asset)
                
                if open_prices is None or open_prices.empty:
                    continue
                
                # Calculate correlation
                correlation = self.calculate_correlation(
                    cand_prices["close"],
                    open_prices["close"],
                )
                
                if abs(correlation) > abs(max_corr):
                    max_corr = correlation
                    max_corr_asset = open_asset
                
                # Veto if too correlated
                if correlation >= self.max_correlation:
                    logger.warning(
                        f"🔗 CORRELATION VETO: {cand_symbol} is {correlation*100:.1f}% correlated "
                        f"with open trade {open_asset}. Skipping to prevent overexposure."
                    )
                    return False, f"high_correlation_with_{open_asset}_{correlation*100:.0f}%"
            
            # Allowed if we got here
            if max_corr > 0.5:
                logger.info(
                    f"[CorrelationGuard] {cand_symbol} allowed (max correlation: "
                    f"{max_corr*100:.1f}% with {max_corr_asset})"
                )
            else:
                logger.debug(f"[CorrelationGuard] {cand_symbol} allowed (no significant correlation)")
            
            return True, "ok"
            
        except Exception as e:
            logger.error(f"[CorrelationGuard] Correlation check failed: {e}")
            # Fail open to avoid blocking trades on errors
            return True, f"error_{str(e)[:30]}"
    
    async def get_open_trades(self) -> List[Dict[str, Any]]:
        """
        Get list of currently open trades from database.
        
        Returns:
            List of trade dicts with 'asset', 'direction' fields
        """
        try:
            from db.session import get_session
            from db.models import Signal
            from sqlalchemy import select
            
            async with get_session() as session:
                result = await session.execute(
                    select(Signal.asset, Signal.direction).where(
                        Signal.expired.is_(False),
                        Signal.archived.is_(False),
                    )
                )
                rows = result.fetchall()
                
                trades = []
                for row in rows:
                    trades.append({
                        "asset": row[0],
                        "direction": row[1],
                    })
                
                logger.debug(f"[CorrelationGuard] Found {len(trades)} open trades")
                return trades
                
        except Exception as e:
            logger.debug(f"[CorrelationGuard] Failed to get open trades: {e}")
            return []
    
    async def check_and_veto(
        self,
        candidate_asset: str,
        candidate_direction: str,
    ) -> Tuple[bool, str]:
        """
        Full check with automatic open trade fetch.
        
        Args:
            candidate_asset: Symbol being considered
            candidate_direction: 'LONG' or 'SHORT'
            
        Returns:
            Tuple of (should_veto: bool, reason: str)
        """
        # First check: don't correlate opposing directions
        # (e.g., LONG BTC and SHORT BTC are naturally hedged)
        direction = str(candidate_direction or "").lower().strip()
        
        # Get open trades
        open_trades = await self.get_open_trades()
        
        # Filter to same direction only (opposing direction = hedge)
        same_direction_trades = [
            t for t in open_trades
            if str(t.get("direction") or "").lower() == direction
        ]
        
        # Check correlation
        return await self.is_trade_allowed(
            candidate_asset=candidate_asset,
            open_trades=same_direction_trades,
        )
    
    def clear_cache(self) -> None:
        """Clear price history cache."""
        self._price_cache.clear()
        logger.debug("[CorrelationGuard] Cache cleared")


class PortfolioCorrelationGuard:
    """
    High-level wrapper for portfolio correlation protection.
    
    Integrates with existing exposure manager for complete protection.
    """
    
    def __init__(self):
        self.correlation_manager = CorrelationManager()
        
        # Try to integrate with existing exposure manager
        try:
            from engine.correlation_filter import exposure_manager
            self.exposure_manager = exposure_manager
        except Exception:
            self.exposure_manager = None
    
    async def is_trade_allowed(
        self,
        asset: str,
        asset_class: str,
        direction: str,
    ) -> Tuple[bool, str]:
        """
        Check both exposure AND correlation limits.
        
        Args:
            asset: Trading symbol
            asset_class: 'crypto', 'fx', etc.
            direction: 'long' or 'short'
            
        Returns:
            Tuple of (is_allowed: bool, reason: str)
        """
        # First check: existing exposure manager
        if self.exposure_manager:
            try:
                exposure_ok = await self.exposure_manager.is_trade_allowed(
                    session=None,
                    asset_class=asset_class,
                    direction=direction,
                )
                if not exposure_ok:
                    return False, "exposure_limit_reached"
            except Exception as e:
                logger.debug(f"[CorrelationGuard] Exposure check failed: {e}")
        
        # Second check: correlation guard
        corr_allowed, corr_reason = await self.correlation_manager.check_and_veto(
            candidate_asset=asset,
            candidate_direction=direction,
        )
        
        if not corr_allowed:
            return False, corr_reason
        
        return True, "ok"
    
    async def filter_signals(
        self,
        signals: List[Dict[str, Any]],
        asset_class: str = "crypto",
    ) -> List[Dict[str, Any]]:
        """
        Filter a list of signals for correlation compliance.
        
        Args:
            signals: List of signal dicts
            asset_class: Asset class for exposure check
            
        Returns:
            Filtered list of signals
        """
        filtered = []
        
        for sig in signals:
            asset = str(sig.get("asset") or "").upper().strip()
            direction = str(sig.get("direction") or "long").lower().strip()
            
            allowed, reason = await self.is_trade_allowed(
                asset=asset,
                asset_class=asset_class,
                direction=direction,
            )
            
            if allowed:
                filtered.append(sig)
            else:
                logger.info(f"[CorrelationGuard] Vetoed {asset}: {reason}")
        
        return filtered


# Default instance
default_correlation_guard = PortfolioCorrelationGuard()


async def check_correlation(
    asset: str,
    direction: str = "long",
) -> Tuple[bool, str]:
    """
    Convenience function to check correlation.
    
    Usage:
        from engine.correlation_guard import check_correlation
        allowed, reason = await check_correlation("SOLUSDT", "long")
    """
    return await default_correlation_guard.check_and_veto(
        candidate_asset=asset,
        candidate_direction=direction,
    )
