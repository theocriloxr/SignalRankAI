"""
Smart Execution Router - Maker vs. Taker Fee Optimization

This module optimizes execution strategy to minimize fees:
- LIMIT orders (Maker): 0% - 0.01% fees (often rebates)
- MARKET orders (Taker): 0.04% - 0.05% fees

The router decides based on:
- ADX (trending/volatile = use MARKET)
- Signal urgency (Squeeze = use MARKET)
- Order book depth (thick = use LIMIT)

Usage:
    from engine.execution_router import SmartRouter
    
    router = SmartRouter()
    strategy = await router.get_execution_decision(asset, urgency, adx)
"""

import logging
import os
from typing import Dict, Any, Optional

logger = logging.getLogger("ExecutionRouter")

# Feature toggle
EXECUTION_ROUTER_ENABLED = os.getenv("EXECUTION_ROUTER_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}

# Fee configuration (percentage)
MAKER_FEE = float(os.getenv("MAKER_FEE_PCT", "0.01"))
TAKER_FEE = float(os.getenv("TAKER_FEE_PCT", "0.05"))
HIGH_ADX_THRESHOLD = float(os.getenv("EXECUTION_HIGH_ADX", "40.0"))


class SmartRouter:
    """
    Determines optimal execution strategy (LIMIT vs MARKET).
    
    In crypto:
    - Maker fees: 0% - 0.01%
    - Taker fees: 0.04% - 0.05%
    
    Saving 0.04% per trade adds up massively over 1000 trades.
    """
    
    def __init__(
        self,
        high_adx_threshold: float = HIGH_ADX_THRESHOLD,
    ):
        self.high_adx_threshold = high_adx_threshold
    
    async def get_execution_decision(
        self,
        asset: str,
        signal_urgency: str = "NORMAL",
        current_adx: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Get execution decision for a signal.
        
        Args:
            asset: Trading symbol
            signal_urgency: 'NORMAL', 'HIGH', 'SQUEEZE'
            current_adx: Optional ADX value
            
        Returns:
            Dict with order_type, urgency, reason, estimated_fee, fee_savings
        """
        if not EXECUTION_ROUTER_ENABLED:
            return self._default_strategy()
        
        try:
            # High ADX = violent movement = must use MARKET
            if current_adx and float(current_adx) > self.high_adx_threshold:
                return {
                    "order_type": "MARKET",
                    "urgency": "HIGH",
                    "reason": f"High ADX ({current_adx:.1f}) requires immediate execution",
                    "estimated_fee": TAKER_FEE,
                    "fee_savings": 0,
                }
            
            # High urgency (squeeze) = use MARKET
            if signal_urgency and signal_urgency.upper() in ("HIGH", "SQUEEZE", "URGENT"):
                return {
                    "order_type": "MARKET",
                    "urgency": signal_urgency.upper(),
                    "reason": f"Signal urgency {signal_urgency} requires MARKET",
                    "estimated_fee": TAKER_FEE,
                    "fee_savings": 0,
                }
            
            # Normal conditions = use LIMIT (Maker)
            # Get current spread to estimate savings
            spread_savings = await self._estimate_spread_savings(asset)
            
            return {
                "order_type": "LIMIT",
                "urgency": "NORMAL",
                "reason": "Stable regime - using LIMIT for maker fees",
                "estimated_fee": MAKER_FEE,
                "fee_savings": TAKER_FEE - MAKER_FEE + spread_savings,
            }
            
        except Exception as e:
            logger.debug(f"[exec_router] Decision failed: {e}")
            return self._default_strategy()
    
    async def _estimate_spread_savings(self, asset: str) -> float:
        """
        Estimate typical spread savings for an asset.
        
        Returns estimated spread benefit (usually very small for liquid pairs).
        """
        # Liquid pairs have tiny spreads
        liquid_pairs = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"}
        
        if asset.upper() in liquid_pairs:
            return 0.01  # ~0.01% typical spread
        return 0.02  # Slightly higher for others
    
    def _default_strategy(self) -> Dict[str, Any]:
        """Default fallback strategy."""
        return {
            "order_type": "MARKET",
            "urgency": "NORMAL",
            "reason": "fallback",
            "estimated_fee": TAKER_FEE,
            "fee_savings": 0,
        }
    
    def format_execution_message(self, strategy: Dict[str, Any]) -> str:
        """Format execution strategy for Telegram."""
        order = strategy.get("order_type", "MARKET")
        urgent = strategy.get("urgency", "NORMAL")
        reason = strategy.get("reason", "")
        fee = strategy.get("estimated_fee", TAKER_FEE) * 100
        savings = strategy.get("fee_savings", 0) * 100
        
        if order == "LIMIT":
            return (
                f"📗 Execution: LIMIT (Maker)\n"
                f"Fee Est: {fee:.2f}%\n"
                f"Potential Savings: {savings:.2f}%\n"
                f"{reason}"
            )
        else:
            return (
                f"📕 Execution: MARKET (Taker)\n"
                f"Fee Est: {fee:.2f}%\n"
                f"{reason}"
            )


# Default instance
_default_router = None


def get_router() -> SmartRouter:
    """Get default router instance."""
    global _default_router
    if _default_router is None:
        _default_router = SmartRouter()
    return _default_router


async def get_execution_strategy(
    asset: str,
    urgency: str = "NORMAL",
    adx: Optional[float] = None,
) -> Dict[str, Any]:
    """Convenience function."""
    router = get_router()
    return await router.get_execution_decision(asset, urgency, adx)
