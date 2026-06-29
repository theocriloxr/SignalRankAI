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

INFLOW_SPIKE_MULTIPLIER = float(os.getenv("ONCHAIN_INFLOW_SPIKE", "5.0"))
MIN_NET_FLOW = float(os.getenv("ONCHAIN_MIN_NET_FLOW", "0.0"))


class OnChainAlpha:
    """
    On-chain data analyzer for whale detection.
    
    Uses configured providers in data.alternative_providers.
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
            return await self._check_exchange_inflows(base, direction)
            
        except Exception as e:
            logger.debug(f"[onchain] Check failed: {e}")
            # Fail open - allow trade if check fails
            return False, f"onchain_error_{str(e)[:20]}"
    
    async def _check_exchange_inflows(self, asset: str, direction: str = "long") -> Tuple[bool, str]:
        """Check configured on-chain context for exchange-flow vetoes."""
        try:
            from data.alternative_providers import fetch_onchain_context

            context = await fetch_onchain_context(asset)
            source = str(context.get("onchain_source") or "none")
            inflow = float(context.get("exchange_inflow") or 0.0)
            outflow = float(context.get("exchange_outflow") or 0.0)
            net_flow = float(context.get("exchange_net_flow") or 0.0)

            if source == "none" or (inflow == 0.0 and outflow == 0.0 and net_flow == 0.0):
                return False, "onchain_no_provider_data"

            inflow_outflow_ratio = inflow / max(outflow, 1e-9)
            direction_norm = str(direction or "").lower()

            if direction_norm == "long":
                if net_flow > MIN_NET_FLOW and inflow_outflow_ratio >= INFLOW_SPIKE_MULTIPLIER:
                    return True, (
                        f"exchange_inflow_spike source={source} "
                        f"inflow={inflow:.4f} outflow={outflow:.4f} net={net_flow:.4f}"
                    )
            elif direction_norm == "short":
                outflow_inflow_ratio = outflow / max(inflow, 1e-9)
                if net_flow < -MIN_NET_FLOW and outflow_inflow_ratio >= INFLOW_SPIKE_MULTIPLIER:
                    return True, (
                        f"exchange_outflow_spike source={source} "
                        f"inflow={inflow:.4f} outflow={outflow:.4f} net={net_flow:.4f}"
                    )

            return False, f"no_spike_detected source={source}"
            
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
        
        should_veto, reason = await self._check_exchange_inflows(base, "long")
        return should_veto, reason


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
