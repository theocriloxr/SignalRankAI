"""
Correlation Engine - Prevent Over-Exposure to Correlated Assets

This engine prevents signal spam across correlated assets like:
- JPY pairs: AUDJPY, CADJPY, NZDJPY, GBPJPY
- USD index: DXY, USDJPY, USDCHF
- Gold: XAUUSD, XAGUSD, GLD ETF
- Oil: WTI, Brent, US Oil Fund
- Indices: SPX, NDX, DJI

The engine tracks:
- Active exposure per correlation group
- Direction bias (long/short/mixed)
- Total risk score

Usage:
    from engine.correlation_engine import (
        check_correlation_allowed,
        get_exposure_summary,
        register_signal,
        clear_expired_signals,
    )
    
    # Check before sending signal
    allowed, reason = await check_correlation_allowed("BTCUSDT", "long", "1h")
    if not allowed:
        # Skip - too much correlated exposure
        return
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from utils.timeutils import now_utc_naive

logger = logging.getLogger(__name__)


# Correlation groups (assets that move together)
CORRELATION_GROUPS: Dict[str, Set[str]] = {
    # JPY crosses (all negatively correlated to JPY strength)
    "jpy": {
        "AUDJPY", "CADJPY", "NZDJPY", "GBPJPY",
        "EURJPY", "CHFJPY", "USDJPY",
    },
    # USD index basket
    "usd": {
        "DXY", "USDJPY", "USDCHF", "USDCAD", "USDNOK", "USDRUB",
    },
    # Gold/Silver
    "precious_metals": {
        "XAUUSD", "XAGUSD", "GLD", "SLV", "PPLT", "PALL",
    },
    # Oil
    "oil": {
        "CLUSD", "BRN", "USO", "USL", "DBO",
    },
    # Crypto majors (BTC/ETH correlation)
    "crypto_majors": {
        "BTCUSDT", "ETHUSDT", "BNBUSDT",
    },
    # Tech stocks
    "tech": {
        "AAPL", "MSFT", "GOOGL", "NVDA", "META", "TSLA",
    },
    # Banks/Financial
    "financial": {
        "JPM", "BAC", "WFC", "GS", "MS", "C",
    },
    # Energy sector
    "energy": {
        "XOM", "CVX", "COP", "SLB", "EOG",
    },
    # European indices
    "european_indices": {
        "DAX", "CAC", "FTSE", "STOXX", "S&P MIB",
    },
    # Asian indices  
    "asian_indices": {
        "NIKKEI", "HSI", "SSEC", "NIFTY", "KOSPI",
    },
}


# Asset to group mapping (for fast lookup)
_ASSET_TO_GROUPS: Dict[str, Set[str]] = {}
for group_name, assets in CORRELATION_GROUPS.items():
    for asset in assets:
        if asset not in _ASSET_TO_GROUPS:
            _ASSET_TO_GROUPS[asset] = set()
        _ASSET_TO_GROUPS[asset].add(group_name)


# Timeframe-specific exposure windows (in hours)
EXPOSURE_WINDOWS = {
    "15m": 4,
    "1h": 12,
    "4h": 24,
    "1d": 72,
    "1w": 168,
}


# Max signals per correlation group
MAX_GROUP_EXPOSURE = {
    "jpy": 2,
    "usd": 3,
    "precious_metals": 1,
    "oil": 1,
    "crypto_majors": 2,
    "tech": 2,
    "financial": 2,
    "energy": 2,
    "european_indices": 1,
    "asian_indices": 1,
}


@dataclass
class SignalExposure:
    """Track signal exposure for correlation check."""
    signal_id: str
    asset: str
    direction: str
    timeframe: str
    created_at: datetime
    expires_at: datetime
    groups: Set[str] = field(default_factory=set)
    score: float = 1.0


class CorrelationEngine:
    """
    Engine to prevent over-exposure to correlated assets.
    
    Maintains in-memory state of active signals per correlation group.
    """
    
    def __init__(self):
        self._exposures: Dict[str, SignalExposure] = {}
        self._cleanup_interval = 3600  # 1 hour
        self._last_cleanup = time.time()
    
    def _cleanup_expired(self) -> None:
        """Remove expired exposures."""
        now = now_utc_naive()
        expired = [
            sid for sid, exp in self._exposures.items()
            if exp.expires_at < now
        ]
        for sid in expired:
            self._exposures.pop(sid, None)
        
        if expired:
            logger.debug(f"[correlation] Cleaned up {len(expired)} expired exposures")
        
        self._last_cleanup = time.time()
    
    def _get_groups_for_asset(self, asset: str) -> Set[str]:
        """Get correlation groups for an asset."""
        # Normalize asset
        normalized = asset.upper().strip()
        
        # Direct lookup
        if normalized in _ASSET_TO_GROUPS:
            return _ASSET_TO_GROUPS[normalized]
        
        # Try base + quote
        base = normalized[:3] if len(normalized) >= 3 else normalized
        if base in _ASSET_TO_GROUPS:
            return _ASSET_TO_GROUPS[base]
        
        return set()
    
    def _get_exposure_window(self, timeframe: str) -> int:
        """Get exposure window in hours for timeframe."""
        return EXPOSURE_WINDOWS.get(timeframe.lower(), 12)
    
    async def check_allowed(
        self,
        asset: str,
        direction: str,
        timeframe: str,
    ) -> Tuple[bool, str]:
        """
        Check if signal is allowed based on correlation limits.
        
        Args:
            asset: Asset symbol
            direction: "long" or "short"
            timeframe: Signal timeframe
            
        Returns:
            (allowed, reason) tuple
        """
        # Periodic cleanup
        if time.time() - self._last_cleanup > self._cleanup_interval:
            self._cleanup_expired()
        
        now = now_utc_naive()
        window_hours = self._get_exposure_window(timeframe)
        cutoff = now - timedelta(hours=window_hours)
        
        # Get correlation groups for this asset
        groups = self._get_groups_for_asset(asset)
        if not groups:
            return True, "no_groups"  # Unknown asset, allow
        
        # Check each group
        for group in groups:
            max_allowed = MAX_GROUP_EXPOSURE.get(group, 2)
            
            # Count signals in this group within window
            group_signals = [
                exp for exp in self._exposures.values()
                if group in exp.groups and exp.created_at >= cutoff
            ]
            
            if len(group_signals) >= max_allowed:
                return False, f"group_{group}_maxed"
            
            # Check direction bias - don't allow same direction on >2 assets in group
            same_direction = [
                exp for exp in group_signals
                if exp.direction.lower() == direction.lower()
            ]
            
            if len(same_direction) >= max_allowed - 1:
                return False, f"group_{group}_direction_bias"
        
        return True, "allowed"
    
    async def register_exposure(
        self,
        signal_id: str,
        asset: str,
        direction: str,
        timeframe: str,
        signal_ttl_hours: Optional[int] = None,
    ) -> None:
        """Register a new signal exposure."""
        now = now_utc_naive()
        window = signal_ttl_hours or self._get_exposure_window(timeframe)
        
        exposure = SignalExposure(
            signal_id=signal_id,
            asset=asset.upper().strip(),
            direction=direction.lower(),
            timeframe=timeframe.lower(),
            created_at=now,
            expires_at=now + timedelta(hours=window),
            groups=self._get_groups_for_asset(asset),
        )
        
        self._exposures[signal_id] = exposure
        logger.debug(
            f"[correlation] Registered {signal_id} for groups: {exposure.groups}"
        )
    
    async def unregister_exposure(self, signal_id: str) -> None:
        """Remove signal exposure."""
        self._exposures.pop(signal_id, None)
    
    async def get_exposure_summary(self, group: Optional[str] = None) -> Dict[str, Any]:
        """Get current exposure summary."""
        now = now_utc_naive()
        
        if group:
            # Specific group
            signals = [
                exp for exp in self._exposures.values()
                if group in exp.groups and exp.expires_at > now
            ]
            return {
                "group": group,
                "signal_count": len(signals),
                "total_score": sum(s.score for s in signals),
                "signals": [
                    {
                        "signal_id": s.signal_id,
                        "asset": s.asset,
                        "direction": s.direction,
                        "timeframe": s.timeframe,
                    }
                    for s in signals
                ],
            }
        
        # All groups
        summary = {}
        for group_name in CORRELATION_GROUPS.keys():
            signals = [
                exp for exp in self._exposures.values()
                if group_name in exp.groups and exp.expires_at > now
            ]
            if signals:
                summary[group_name] = {
                    "signal_count": len(signals),
                    "total_score": sum(s.score for s in signals),
                    "assets": list(set(s.asset for s in signals)),
                    "directions": list(set(s.direction for s in signals)),
                }
        
        return summary
    
    async def clear_all(self) -> None:
        """Clear all exposures."""
        self._exposures.clear()
        logger.info("[correlation] Cleared all exposures")


# Singleton instance
_correlation_engine: Optional[CorrelationEngine] = None


def get_correlation_engine() -> CorrelationEngine:
    """Get or create the CorrelationEngine singleton."""
    global _correlation_engine
    if _correlation_engine is None:
        _correlation_engine = CorrelationEngine()
    return _correlation_engine


# Convenience functions
async def check_correlation_allowed(
    asset: str,
    direction: str,
    timeframe: str,
) -> Tuple[bool, str]:
    """Check if signal is allowed."""
    engine = get_correlation_engine()
    return await engine.check_allowed(asset, direction, timeframe)


async def register_signal(
    signal_id: str,
    asset: str,
    direction: str,
    timeframe: str,
    ttl_hours: Optional[int] = None,
) -> None:
    """Register signal exposure."""
    engine = get_correlation_engine()
    await engine.register_exposure(signal_id, asset, direction, timeframe, ttl_hours)


async def get_exposure_summary(group: Optional[str] = None) -> Dict[str, Any]:
    """Get exposure summary."""
    engine = get_correlation_engine()
    return await engine.get_exposure_summary(group)


async def clear_expired_signals() -> None:
    """Clear expired signals."""
    engine = get_correlation_engine()
    engine._cleanup_expired()


__all__ = [
    "CorrelationEngine",
    "get_correlation_engine",
    "check_correlation_allowed",
    "register_signal",
    "get_exposure_summary",
    "clear_expired_signals",
    "CORRELATION_GROUPS",
    "MAX_GROUP_EXPOSURE",
]
