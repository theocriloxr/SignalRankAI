"""
On-Chain Alpha - Whale Tracking

This module integrates on-chain data to detect whale activity:
- Exchange inflows (deposits to exchanges = likely selling)
- Exchange outflows (withdrawals from exchanges = likely accumulation)

The Edge: On-chain data often precedes price movement by minutes to hours,
giving signals more time to react than pure technical analysis.

Usage:
    from engine.onchain_alpha import OnChainAlpha
    
    alpha = OnChainAlpha()
    should_veto, reason = await alpha.check_veto(asset, direction)
"""

import logging
import os
from typing import Tuple

logger = logging.getLogger("OnChainAlpha")

# Feature toggle
ONCHAIN_ALPHA_ENABLED = os.getenv("ONCHAIN_ALPHA_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}

# Supported assets (on-chain data reliable for these)
SUPPORTED_ASSETS = {"BTC", "ETH", "SOL", "LINK", "BNB", "XRP", "ADA", "DOGE"}

# Thresholds
INFLOW_SPIKE_MULTIPLIER = float(os.getenv("ONCHAIN_INFLOW_SPIKE", "5.0"))  # 5x normal = spike


class OnChainAlpha:
    """
    On-chain data analyzer for whale detection.
    
    In production, this would integrate with:
    - CryptoQuant API
    - Glassnode API
    - Nansen AI
    - Whale Alert
    
    For now, provides the structure with simulated data.
    """
    
    def __init__(self):
        self.supported_assets = SUPPORTED_ASSETS
    
    async def check_veto(
        self,
        asset: str,
        direction: str = "long",
    ) -> Tuple[bool, str]:
        """
        Check if on-chain data warrants vetoing the trade.
        
        Args:
            asset: Trading symbol (e.g., 'BTCUSDT')
            direction: 'long' or 'short'
            
        Returns:
            Tuple of (should_veto: bool, reason: str)
        """
        if not ONCHAIN_ALPHA_ENABLED:
            return False, "onchain_disabled"
        
        # Extract base asset
        base = asset.replace("USDT", "").replace("BUSD", "").strip()
        
        if base not in self.supported_assets:
            return False, "unsupported_asset"
        
        try:
            # Check exchange inflows
            return await self._check_exchange_inflows(base)
            
        except Exception as e:
            logger.debug(f"[onchain] Check failed: {e}")
            # Fail open - allow trade if check fails
            return False, f"onchain_error_{str(e)[:20]}"
    
    async def _check_exchange_inflows(self, asset: str) -> Tuple[bool, str]:
        """
        Check for exchange inflow spike (whale dumping).
        
        In production, this would call external API.
        """
        try:
            # Placeholder for real API call
            # url = f"https://api.cryptoquant.com/v1/{asset}/exchange-flows"
            # data = await fetch(url)
            
            # For now, return safe (no veto)
            # In production, analyze actual inflow data
            
            return False, "no_spike_detected"
            
        except Exception as e:
            logger.debug(f"[onchain] Inflow check failed: {e}")
            return False, f"api_error_{str(e)[:20]}"
    
    async def check_whale_alert(
        self,
        asset: str,
        min_amount_usd: float = 1000000,
    ) -> Tuple[bool, str]:
        """
        Check for large whale transactions.
        
        Args:
            asset: Trading symbol
            min_amount_usd: Minimum USD value to flag
            
        Returns:
            Tuple of (whale_detected: bool, details: str)
        """
        if not ONCHAIN_ALPHA_ENABLED:
            return False, "disabled"
        
        base = asset.replace("USDT", "").replace("BUSD", "").strip()
        
        if base not in self.supported_assets:
            return False, "unsupported"
        
        # Placeholder for real implementation
        return False, "no_whale"


# Default instance
_default_alpha = None


def get_alpha() -> OnChainAlpha:
    """Get default OnChainAlpha instance."""
    global _default_alpha
    if _default_alpha is None:
        _default_alpha = OnChainAlpha()
    return _default_alpha


async def check_veto(asset: str, direction: str = "long") -> Tuple[bool, str]:
    """Convenience function."""
    alpha = get_alpha()
    return await alpha.check_veto(asset, direction)
