"""
Endgame Features Integration Module

This module integrates the four "Endgame" features into the existing SignalRankAI pipeline:
1. Auto-Optimizer (Self-Healing Risk Management)
2. Smart Execution Router (Maker vs. Taker)
3. On-Chain Alpha (Whale Tracking)
4. Correlation Guard (Portfolio Protection)

These features work together to create an institutional-grade trading engine.

Usage:
    from engine.endgame_integration import (
        get_execution_strategy_for_signal,
        check_onchain_veto,
        check_correlation_veto,
        run_weekly_optimization,
    )
"""

import logging
import os
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("EndgameIntegration")

# Feature toggles
ENDGAME_ENABLED = os.getenv("ENDGAME_FEATURES_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
EXECUTION_ROUTER_ENABLED = os.getenv("EXECUTION_ROUTER_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
ONCHAIN_ALPHA_ENABLED = os.getenv("ONCHAIN_ALPHA_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
CORRELATION_GUARD_ENABLED = os.getenv("CORRELATION_GUARD_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}


# ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
# 1. EXECUTION ROUTER - Maker vs. Taker Fee Optimization
# ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def get_execution_strategy_for_signal(
    signal: Dict[str, Any],
    current_adx: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Get execution strategy (LIMIT vs MARKET) for a signal.
    
    Args:
        signal: Signal dictionary with 'asset', 'direction', etc.
        current_adx: Optional ADX value from indicators
        
    Returns:
        Dict with 'order_type', 'urgency', 'reason', 'estimated_fee', 'fee_savings'
    """
    if not EXECUTION_ROUTER_ENABLED:
        return {
            "order_type": "MARKET",
            "urgency": "NORMAL",
            "reason": "execution_router_disabled",
            "estimated_fee": 0.05,
            "fee_savings": 0,
        }
    
    try:
        from engine.execution_router import SmartRouter
        router = SmartRouter()
        
        asset = signal.get("asset", "")
        signal_urgency = signal.get("urgency", "NORMAL")
        
        strategy = await router.get_execution_decision(
            asset=asset,
            signal_urgency=signal_urgency,
            current_adx=current_adx,
        )
        
        # Attach to signal for downstream use
        signal["execution_strategy"] = strategy
        
        return strategy
        
    except Exception as e:
        logger.debug(f"[endgame] Execution router failed: {e}")
        return {
            "order_type": "MARKET",
            "urgency": "NORMAL",
            "reason": "fallback_error",
            "estimated_fee": 0.05,
            "fee_savings": 0,
        }


def format_execution_message(strategy: Dict[str, Any]) -> str:
    """Format execution strategy for Telegram message."""
    try:
        from engine.execution_router import SmartRouter
        router = SmartRouter()
        return router.format_execution_message(strategy)
    except Exception:
        order = strategy.get("order_type", "MARKET")
        fee = strategy.get("estimated_fee", 0.05) * 100
        return f"📕 Execution: {order}\nFee Est: {fee:.2f}%"


# ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
# 2. ON-CHAIN ALPHA - Whale Tracking
# ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def check_onchain_veto(
    signal: Dict[str, Any],
) -> Tuple[bool, str]:
    """
    Check if on-chain data warrants vetoing the signal.
    
    Args:
        signal: Signal dictionary with 'asset', 'direction'
        
    Returns:
        Tuple of (should_veto: bool, reason: str)
    """
    if not ONCHAIN_ALPHA_ENABLED:
        return False, "onchain_disabled"
    
    try:
        from engine.onchain_alpha import OnChainAlpha
        alpha = OnChainAlpha()
        
        asset = signal.get("asset", "")
        direction = signal.get("direction", "long")
        
        return await alpha.check_veto(asset, direction)
        
    except Exception as e:
        logger.debug(f"[endgame] On-chain check failed: {e}")
        # Fail open - allow trade if check fails
        return False, f"onchain_check_error_{str(e)[:20]}"


async def check_all_vetos_for_signal(
    signal: Dict[str, Any],
    current_adx: Optional[float] = None,
) -> Tuple[bool, str]:
    """
    Run all veto checks for a signal.
    
    Checks in order:
    1. On-chain whale detection (if enabled)
    2. Execution strategy (informational only)
    
    Args:
        signal: Signal dictionary
        current_adx: Optional ADX value
        
    Returns:
        Tuple of (should_veto: bool, reason: str)
    """
    if not ENDGAME_ENABLED:
        return False, "endgame_disabled"
    
    # Check on-chain veto
    if ONCHAIN_ALPHA_ENABLED:
        onchain_veto, onchain_reason = await check_onchain_veto(signal)
        if onchain_veto:
            logger.warning(f"[endgame] ONCHAIN VETO: {signal.get('asset')} - {onchain_reason}")
            return True, onchain_reason
    
    # Get execution strategy (doesn't veto, just informs)
    if EXECUTION_ROUTER_ENABLED:
        try:
            await get_execution_strategy_for_signal(signal, current_adx)
        except Exception as e:
            logger.debug(f"[endgame] Execution strategy failed: {e}")
    
    return False, "ok"


# ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
# 3. CORRELATION GUARD - Portfolio Correlation Prevention
# ──────────────────────────────────────��──────────────────────────────────────────────────────────────────────

async def check_correlation_veto(
    candidate_asset: str,
    candidate_direction: str = "long",
) -> Tuple[bool, str]:
    """
    Check if candidate is too correlated with existing open trades.
    
    Args:
        candidate_asset: Symbol being considered
        candidate_direction: 'long' or 'short'
        
    Returns:
        Tuple of (should_veto: bool, reason: str)
    """
    if not CORRELATION_GUARD_ENABLED:
        return True, "correlation_guard_disabled"
    
    try:
        from engine.correlation_guard import CorrelationManager
        manager = CorrelationManager()
        
        return await manager.check_and_veto(
            candidate_asset=candidate_asset,
            candidate_direction=candidate_direction,
        )
        
    except Exception as e:
        logger.debug(f"[endgame] Correlation check failed: {e}")
        # Fail open to avoid blocking trades on errors
        return True, f"correlation_check_error_{str(e)[:20]}"


async def filter_signals_for_correlation(
    signals: list[Dict[str, Any]],
    asset_class: str = "crypto",
) -> list[Dict[str, Any]]:
    """
    Filter signals for correlation compliance.
    
    Args:
        signals: List of signal dictionaries
        asset_class: Asset class ('crypto', 'fx', etc.)
        
    Returns:
        Filtered list of signals
    """
    if not CORRELATION_GUARD_ENABLED:
        return signals
    
    try:
        from engine.correlation_guard import PortfolioCorrelationGuard
        guard = PortfolioCorrelationGuard()
        
        return await guard.filter_signals(signals, asset_class)
        
    except Exception as e:
        logger.debug(f"[endgame] Signal filtering failed: {e}")
        return signals


# ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
# 4. AUTO-OPTIMIZER - Self-Healing Risk Management
# ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def run_weekly_optimization() -> Optional[Dict[str, Any]]:
    """
    Run the weekly auto-optimization analysis.
    
    Returns:
        Optimization result dict or None
    """
    if not ENDGAME_ENABLED:
        logger.debug("[endgame] Endgame disabled, skipping auto-optimization")
        return None
    
    try:
        from engine.auto_optimizer import AutoOptimizerRunner
        runner = AutoOptimizerRunner()
        
        result = await runner.run_optimization()
        
        if result:
            return {
                "recommended_sl": result.recommended_sl,
                "current_sl": result.current_sl,
                "confidence": result.confidence,
                "trade_count": result.analysis_trade_count,
                "reasoning": result.reasoning,
            }
        return None
        
    except Exception as e:
        logger.debug(f"[endgame] Auto-optimization failed: {e}")
        return None


# ──────────────────────────────────────────────────��─��────────────────────────────────────────────────────────
# Integration Helper Functions
# ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

def get_endgame_status() -> Dict[str, Any]:
    """
    Get status of all endgame features.
    
    Returns:
        Dict with feature names and enabled status
    """
    return {
        "endgame_enabled": ENDGAME_ENABLED,
        "execution_router_enabled": EXECUTION_ROUTER_ENABLED,
        "onchain_alpha_enabled": ONCHAIN_ALPHA_ENABLED,
        "correlation_guard_enabled": CORRELATION_GUARD_ENABLED,
    }


async def enrich_signal_with_endgame(
    signal: Dict[str, Any],
    current_adx: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Enrich a signal with all endgame analysis.
    
    This is the main integration point - call this function
    after a signal passes initial validation to add:
    - Execution strategy (LIMIT vs MARKET)
    - On-chain veto check
    - (Correlation check should be done at portfolio level)
    
    Args:
        signal: Signal dictionary
        current_adx: Optional ADX value
        
    Returns:
        Enriched signal dictionary
    """
    if not ENDGAME_ENABLED:
        return signal
    
    # Add execution strategy
    try:
        strategy = await get_execution_strategy_for_signal(signal, current_adx)
        signal["execution_strategy"] = strategy
    except Exception as e:
        logger.debug(f"[endgame] Failed to add execution strategy: {e}")
    
    # Check on-chain veto
    if ONCHAIN_ALPHA_ENABLED:
        try:
            should_veto, reason = await check_onchain_veto(signal)
            if should_veto:
                signal["rejection_reason"] = f"onchain_veto: {reason}"
                signal["vetoed"] = True
        except Exception as e:
            logger.debug(f"[endgame] On-chain check failed: {e}")
    
    return signal


# ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
# Telegram Message Formatters
# ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

def format_endgame_summary(signal: Dict[str, Any]) -> str:
    """
    Format endgame features for Telegram signal message.
    
    Args:
        signal: Signal dictionary (possibly enriched)
        
    Returns:
        Formatted string for Telegram
    """
    parts = []
    
    # Execution strategy
    exec_strategy = signal.get("execution_strategy")
    if exec_strategy:
        parts.append(format_execution_message(exec_strategy))
    
    # On-chain status
    if signal.get("vetoed"):
        parts.append("⚠️ On-Chain: VETOED")
    elif ONCHAIN_ALPHA_ENABLED:
        parts.append("✅ On-Chain: Safe")
    
    if parts:
        return "\n".join(parts)
    return ""


# Default instance
_default_endgame = None


async def initialize_endgame():
    """Initialize endgame modules (called at startup)."""
    global _default_endgame
    
    status = get_endgame_status()
    logger.info(f"[endgame] Initialized: {status}")
    
    return status
