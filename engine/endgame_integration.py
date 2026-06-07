"""
Endgame Features Integration Module

This module integrates the four "Endgame" institutional-grade features:
1. Auto-Optimizer (Self-Healing Risk Management)
2. Smart Execution Router (Maker vs. Taker)
3. On-Chain Alpha (Whale Tracking) 
4. Correlation Guard (Portfolio Protection)

Usage:
    # Add correlation guard to existing portfolio exposure check in core.py:
    # Replace the existing portfolio_exposure block with:
    
    try:
        _exp_enabled = os.getenv("ENDGAME_FEATURES_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
        if _exp_enabled:
            # NEW: ENDGAME Correlation Guard (replaces existing check)
            from engine.correlation_guard import check_and_veto as _corr_check
            _corr_veto, _corr_reason = run_sync(_corr_check(_asset_name, _direction))
            if _corr_veto:
                logger.info(f"[engine] correlation_guard: skipping {_asset_name} - {_corr_reason}")
                pipeline_stats["skipped_correlation_guard"] = pipeline_stats.get("skipped_correlation_guard", 0) + 1
                continue
    except Exception as _cg_err:
        logger.debug(f"[engine] correlation guard check failed: {_cg_err}")

    # Add Execution Router enrichment after signal is stored:
    try:
        if os.getenv("EXECUTION_ROUTER_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}:
            from engine.execution_router import get_execution_strategy
            _adx = (market_data.get(tf, {}).get('indicators', {}).get('adx', 30)
            _exec_strategy = run_sync(get_execution_strategy(_asset_name, "NORMAL", _adx))
            sig['execution_strategy'] = _exec_strategy
    except Exception as _er_err:
        logger.debug(f"[engine] execution router failed: {_er_err}")

Weekly Auto-Optimizer (add to worker.py):
    # Add new task in worker _register_task section:
    _register_task("auto_optimizer", lambda: self._auto_optimizer_loop())

    # Add method:
    async def _auto_optimizer_loop(self) -> None:
        interval = max(3600, int(os.getenv("AUTO_OPTIMIZER_INTERVAL_SECONDS", "604800")))  # Weekly
        while not self._stop.is_set():
            try:
                from engine.auto_optimizer import run_optimization
                result = await run_optimization()
                if result:
                    logger.info(f"[worker] auto-optimizer: {result.reasoning}")
            except Exception as e:
                logger.warning(f"[worker] auto-optimizer failed: {e}")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

Environment Variables:
    ENDGAME_FEATURES_ENABLED=1        # Enable all endgame features
    EXECUTION_ROUTER_ENABLED=1          # Maker vs Taker routing
    ONCHAIN_ALPHA_ENABLED=0            # Whale tracking (requires API key)
    CORRELATION_GUARD_ENABLED=1        # Portfolio correlation check
    AUTO_OPTIMIZER_ENABLED=1             # Weekly SL optimization
    AUTO_OPTIMIZER_INTERVAL_SECONDS=604800 # Weekly (7 days)
    AUTO_OPT_MIN_TRADES=50               # Min trades before optimization
    AUTO_OPT_TARGET_PERCENTILE=0.90     # 90% of trades should survive
    MAX_CORRELATION=0.85               # Max correlation threshold
    MAX_TRADES_PER_DIRECTION=5            # Max same-direction trades

Feature Descriptions:
    1. Auto-Optimizer:
       Analyzes MAE (Maximum Adverse Excursion) from past winning trades
       If 90% never drop below -1.8%, recommends tighter SL (e.g., -1.9%)
       Runs weekly to continuously improve risk parameters
    
    2. Execution Router:
       High ADX (>40) or SQUEEZE signal -> MARKET order (Taker fees ~0.05%)
       Normal conditions -> LIMIT order (Maker fees ~0.01% or rebates)
       Estimated savings: 0.04% per trade = 40% on 1000 trades
    
    3. On-Chain Alpha:
       Checks exchange inflows (API required: CryptoQuant/Glassnode)
       Massive deposits to exchanges = potential dump = veto LONG
       Enable: ONCHAIN_ALPHA_ENABLED=1 + API configuration
    
    4. Correlation Guard:
       Prevents opening trades on highly correlated assets
       If you have 5 crypto longs and open another -> vetoed
       Prevents portfolio blow-ups from correlated moves

Integration Status:
    ✓ auto_optimizer.py - Implemented
    ✓ execution_router.py - Implemented  
    ✓ onchain_alpha.py - Implemented (API stub)
    ✓ correlation_guard.py - Implemented
    ✓ Integration helper - Use above code snippets in core.py

The features are designed to fail gracefully - if any check fails,
the system continues with conservative defaults.
"""

import logging
import os
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("EndgameIntegration")

# Feature toggles from environment
ENDGAME_ENABLED = os.getenv("ENDGAME_FEATURES_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
EXECUTION_ROUTER_ENABLED = os.getenv("EXECUTION_ROUTER_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
ONCHAIN_ALPHA_ENABLED = os.getenv("ONCHAIN_ALPHA_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
CORRELATION_GUARD_ENABLED = os.getenv("CORRELATION_GUARD_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}


def get_endgame_status() -> Dict[str, bool]:
    """Get current status of all endgame features."""
    return {
        "enabled": ENDGAME_ENABLED,
        "execution_router": EXECUTION_ROUTER_ENABLED,
        "onchain_alpha": ONCHAIN_ALPHA_ENABLED,
        "correlation_guard": CORRELATION_GUARD_ENABLED,
    }


async def enrich_signal_execution(signal: Dict[str, Any], adx: float = 30) -> Dict[str, Any]:
    """
    Enrich signal with execution strategy (Maker vs Taker).
    
    Args:
        signal: Signal dictionary
        adx: ADX indicator value
        
    Returns:
        Enriched signal with execution_strategy key
    """
    if not EXECUTION_ROUTER_ENABLED:
        return signal
        
    try:
        from engine.execution_router import get_execution_strategy
        strategy = await get_execution_strategy(
            signal.get("asset", ""),
            signal.get("urgency", "NORMAL"),
            adx,
        )
        signal["execution_strategy"] = strategy
    except Exception as e:
        logger.debug(f"[endgame] Execution router failed: {e}")
        
    return signal


def format_execution_info(strategy: Dict[str, Any]) -> str:
    """Format execution strategy for Telegram display."""
    if not strategy:
        return ""
        
    order_type = strategy.get("order_type", "MARKET")
    fee = strategy.get("estimated_fee", 0.0005) * 100
    savings = strategy.get("fee_savings", 0) * 100
    
    if order_type == "LIMIT":
        return f"📗 LIMIT: ~{fee:.2f}% (save ~{savings:.2f}%)"
    else:
        return f"📕 MARKET: ~{fee:.2f}%"


# Initialize and log status on import
if ENDGAME_ENABLED:
    logger.info(f"[endgame] Enabled: {get_endgame_status()}")
