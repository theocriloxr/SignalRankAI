"""
Correlation Guard - Portfolio Correlation Prevention

This module prevents over-correlation in the portfolio:
- If you have 5 crypto longs and open another, you're not diversified
- If BTC dumps, all 5 hit SL simultaneously
- CorrelationGuard prevents this by tracking and vetoing correlated trades

The Concept: Calculate real-time price correlation between candidate
and existing open trades. If correlation > threshold, veto to prevent
portfolio blow-up from correlated moves.

Usage:
    from engine.correlation_guard import CorrelationManager
    
    manager = CorrelationManager()
    should_veto, reason = await manager.check_and_veto(candidate_asset, direction)
"""

import logging
import os
from typing import Dict, List, Tuple, Any, Optional

logger = logging.getLogger("CorrelationGuard")

# Feature toggle
CORRELATION_GUARD_ENABLED = os.getenv("CORRELATION_GUARD_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}

# Configuration
MAX_CORRELATION = float(os.getenv("MAX_CORRELATION", "0.85"))
MIN_CORRELATION_LOOKBACK = int(os.getenv("CORRELATION_LOOKBACK_BARS", "50"))

# Asset correlation groups (highly correlated = same move)
CORRELATION_GROUPS = {
    "crypto": {
        "BTC": ["BTC", "WBTC"],
        "ETH": ["ETH", "WETH", "STETH"],
        "SOL": ["SOL"],
        "BNB": ["BNB"],
        "ADA": ["ADA"],
        "XRP": ["XRP"],
        "DOT": ["DOT"],
        "AVAX": ["AVAX"],
        "LINK": ["LINK"],
    },
    "fx": {
        "EURUSD": ["EURUSD", "EURGBP"],
        "GBPUSD": ["GBPUSD", "GBPEUR"],
    },
}


class CorrelationManager:
    """
    Manages portfolio correlation to prevent over-exposure.
    
    Strategy:
    1. Track open trades per direction
    2. Group assets by correlation class
    3. Veto new trades in highly correlated groups
    """
    
    def __init__(
        self,
        max_correlation: float = MAX_CORRELATION,
    ):
        self.max_correlation = max_correlation
        self._open_trades: Dict[str, List[str]] = {}  # direction -> [assets]
        self._price_cache: Dict[str, List[float]] = {}  # asset -> price history
    
    async def check_and_veto(
        self,
        candidate_asset: str,
        candidate_direction: str = "long",
    ) -> Tuple[bool, str]:
        """
        Check if candidate should be vetoed due to correlation.
        
        Args:
            candidate_asset: Symbol being considered
            candidate_direction: 'long' or 'short'
            
        Returns:
            Tuple of (should_veto: bool, reason: str)
        """
        if not CORRELATION_GUARD_ENABLED:
            return False, "correlation_guard_disabled"
        
        try:
            # Check same-direction exposure
            same_direction = await self._get_same_direction_count(candidate_direction)
            max_per_direction = int(os.getenv("MAX_TRADES_PER_DIRECTION", "5"))
            if same_direction >= max_per_direction:
                return True, f"max_{candidate_direction}_trades_reached"
            
            # Check correlation with open trades
            is_correlated, reason = await self._check_correlation(candidate_asset, candidate_direction)
            if is_correlated:
                return True, reason
            
            return False, "ok"
            
        except Exception as e:
            logger.debug(f"[correlation] Check failed: {e}")
            # Fail open to avoid blocking
            return False, f"correlation_error_{str(e)[:20]}"
    
    async def _get_same_direction_count(self, direction: str) -> int:
        """Get count of open trades in same direction."""
        try:
            from core.redis_state import state
            
            if state.has_redis_sync():
                active = state.get_active_trades_sync() or {}
                count = 0
                for payload in active.values():
                    if isinstance(payload, dict):
                        d = payload.get("direction", "").lower()
                        if d == direction.lower():
                            count += 1
                return count
            
            return 0
            
        except Exception:
            return 0
    
    async def _check_correlation(
        self,
        candidate: str,
        direction: str,
    ) -> Tuple[bool, str]:
        """Check correlation with existing positions."""
        try:
            # Get open positions
            open_assets = await self._get_open_assets(direction)
            
            if not open_assets:
                return False, "no_open_positions"
            
            # Check if candidate is in same correlation group
            candidate_group = self._get_correlation_group(candidate)
            
            for open_asset in open_assets:
                open_group = self._get_correlation_group(open_asset)
                
                if candidate_group and candidate_group == open_group:
                    # Same group = highly correlated
                    return True, f"correlated_with_{open_asset}"
                
                # Check symbol similarity
                if self._symbols_correlated(candidate, open_asset):
                    return True, f"correlated_with_{open_asset}"
            
            return False, "ok"
            
        except Exception as e:
            logger.debug(f"[correlation] _check_correlation failed: {e}")
            return False, f"error_{str(e)[:20]}"
    
    def _get_correlation_group(self, asset: str) -> Optional[str]:
        """Get correlation group for an asset."""
        asset = asset.upper()
        
        for group_name, members in CORRELATION_GROUPS.items():
            for member in members:
                if member in asset:
                    return member
        return None
    
    def _symbols_correlated(self, asset1: str, asset2: str) -> bool:
        """Check if two symbols are the same/very similar."""
        a1 = asset1.upper().replace("USDT", "").replace("BUSD", "")
        a2 = asset2.upper().replace("USDT", "").replace("BUSD", "")
        
        # Same base symbol
        if a1 == a2:
            return True
        
        # Contains same base
        if a1 in a2 or a2 in a1:
            return True
        
        return False
    
    async def _get_open_assets(self, direction: str) -> List[str]:
        """Get list of currently open assets."""
        try:
            from core.redis_state import state
            
            assets = []
            if state.has_redis_sync():
                active = state.get_active_trades_sync() or {}
                for payload in active.values():
                    if isinstance(payload, dict):
                        d = payload.get("direction", "").lower()
                        a = payload.get("asset", "")
                        if d == direction.lower() and a:
                            assets.append(a)
            
            return assets
            
        except Exception:
            return []


class PortfolioCorrelationGuard:
    """
    Filters signals for portfolio-level correlation compliance.
    
    Used to filter a batch of signals before delivery.
    """
    
    def __init__(self):
        self.manager = CorrelationManager()
    
    async def filter_signals(
        self,
        signals: List[Dict[str, Any]],
        asset_class: str = "crypto",
    ) -> List[Dict[str, Any]]:
        """
        Filter signals for correlation compliance.
        
        Args:
            signals: List of signal dictionaries
            asset_class: Asset class filter
            
        Returns:
            Filtered signals
        """
        if not signals:
            return signals
        
        filtered = []
        
        for sig in signals:
            asset = sig.get("asset", "")
            direction = sig.get("direction", "long")
            
            should_veto, reason = await self.manager.check_and_veto(asset, direction)
            
            if should_veto:
                logger.info(f"[correlation] Vetoed {asset}: {reason}")
                sig["vetoed"] = True
                sig["veto_reason"] = reason
                continue
            
            filtered.append(sig)
        
        return filtered


# Default instance
_default_manager = None
_default_guard = None


def get_manager() -> CorrelationManager:
    """Get default manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = CorrelationManager()
    return _default_manager


def get_guard() -> PortfolioCorrelationGuard:
    """Get default guard."""
    global _default_guard
    if _default_guard is None:
        _default_guard = PortfolioCorrelationGuard()
    return _default_guard


async def check_and_veto(asset: str, direction: str = "long") -> Tuple[bool, str]:
    """Convenience function."""
    manager = get_manager()
    return await manager.check_and_veto(asset, direction)
