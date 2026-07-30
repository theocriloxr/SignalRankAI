"""Adaptive asset-specific strategy intelligence for SignalRankAI.

The package is deliberately additive: deterministic strategy and risk gates remain
canonical, while approved adaptive profiles can apply bounded weighting and all
candidate evidence is retained for shadow/learning review.
"""
from .runtime import AdaptiveStrategyService, get_adaptive_strategy_service
from .types import AssetStrategyProfile, MarketContext, StrategyEvidence

__all__ = [
    "AdaptiveStrategyService",
    "AssetStrategyProfile",
    "MarketContext",
    "StrategyEvidence",
    "get_adaptive_strategy_service",
]
