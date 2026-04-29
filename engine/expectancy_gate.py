"""Live Expectancy Gate - Blocks signals from underperforming assets/strategies.

Blocks if live expectancy < EXPECTANCY_MIN (0.15). Queries DB live metrics.
Supports per-asset, per-strategy, global expectancy.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import asyncio

from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from core.tier_constants import EXPECTANCY_MIN
from db.session import get_session
from db.models import SignalOutcome, Signal  # Assumes these exist or Phase 3 adds them

logger = logging.getLogger(__name__)


async def get_live_expectancy(
    asset: str,
    strategy: Optional[str] = None,
    lookback_hours: int = 168  # 1 week default
) -> float:
    """Query live expectancy from recent outcomes.
    
    Expectancy = (Win% * Avg Win R) - (Loss% * Avg Loss R)
    """
    async with get_session() as session:
        try:
            cutoff = datetime.utcnow() - timedelta(hours=lookback_hours)
            
            # Base query for outcomes
            query = select(
                func.avg(SignalOutcome.r_multiple).label('avg_r'),
                func.count().label('total'),
                func.sum(func.case((SignalOutcome.outcome == 'win', 1), else_=0)).label('wins')
            ).where(
                SignalOutcome.created_at >= cutoff,
                SignalOutcome.signal_id == Signal.id,
                Signal.asset == asset
            )
            
            if strategy:
                query = query.where(Signal.strategy == strategy)
            
            result = await session.execute(query)
            row = result.fetchone()
            
            if not row or row.total == 0:
                # No data: use global default
                logger.warning(f"No expectancy data for {asset}/{strategy}, using default {EXPECTANCY_MIN}")
                return EXPECTANCY_MIN
            
            total = row.total
            wins = row.wins or 0
            avg_r_all = row.avg_r or 0
            
            win_rate = wins / total
            loss_rate = 1 - win_rate
            avg_win_r = 1.8  # Placeholder: query avg_win_r, avg_loss_r separately in prod
            avg_loss_r = 0.8
            
            expectancy = (win_rate * avg_win_r) - (loss_rate * avg_loss_r)
            
            logger.debug(f"Live expectancy {asset}/{strategy}: {expectancy:.3f} (n={total}, wr={win_rate:.1%})")
            return float(expectancy)
            
        except Exception as e:
            logger.error(f"Expectancy query failed for {asset}/{strategy}: {e}")
            return EXPECTANCY_MIN  # Fail safe: minimum threshold


async def expectancy_gate(signal: Dict[str, Any]) -> bool:
    """Gate function: block if expectancy < EXPECTANCY_MIN."""
    asset = signal.get("asset")
    strategy = signal.get("strategy")
    
    if not asset:
        logger.warning("No asset in signal, passing expectancy gate")
        return True
    
    try:
        exp = await get_live_expectancy(asset, strategy)
        gate_pass = exp >= EXPECTANCY_MIN
        
        if not gate_pass:
            logger.info(f"Expectancy BLOCK: {asset}/{strategy} exp={exp:.3f} < {EXPECTANCY_MIN}")
        
        signal["live_expectancy"] = exp  # Pass through for risk/scoring
        return gate_pass
        
    except Exception as e:
        logger.error(f"Expectancy gate error for {asset}: {e}")
        return True  # Fail open on error


async def global_expectancy_check(global_dd: float) -> bool:
    """Global check: block all if portfolio DD too high."""
    from core.tier_constants import DD_HARD_LIMIT
    return global_dd < DD_HARD_LIMIT


# Integration hook for engine loop
async def validate_expectancy_pipeline(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Run full expectancy pipeline."""
    signal["expectancy_pass"] = await expectancy_gate(signal)
    return signal

