#!/usr/bin/env python3
"""Auto-kill switch for daily loss and monthly drawdown limits."""

import logging
import os
from datetime import datetime, timedelta

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import OWNER_IDS
from db.models import SignalOutcome
from db.session import get_session

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "0.05"))
MAX_MONTHLY_DRAWDOWN = float(os.getenv("MAX_MONTHLY_DRAWDOWN", "0.20"))

SYSTEM_ACTIVE = True


def daily_loss(session: Session) -> float:
    """Sum pnl_pct for signals closed today in UTC."""
    try:
        cutoff = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        total = (
            session.query(func.sum(SignalOutcome.pnl_pct))
            .filter(SignalOutcome.closed_at >= cutoff)
            .scalar()
            or 0.0
        )
        return float(total)
    except Exception:
        logger.exception("daily_loss query failed")
        return 0.0


def monthly_drawdown(session: Session) -> float:
    """Estimate rolling monthly drawdown from recent realized outcome pnl_pct."""
    try:
        cutoff = datetime.utcnow() - timedelta(days=30)
        outcomes = (
            session.query(SignalOutcome)
            .filter(SignalOutcome.closed_at >= cutoff)
            .order_by(SignalOutcome.closed_at.asc())
            .all()
        )
        pnls = [float(o.pnl_pct) for o in outcomes if o.pnl_pct is not None]
        if not pnls:
            return 0.0

        equity = 1.0
        peak = equity
        max_drawdown = 0.0
        for pnl in pnls:
            equity *= 1.0 + pnl
            peak = max(peak, equity)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - equity) / peak)
        return max_drawdown
    except Exception:
        logger.exception("monthly_drawdown query failed")
        return 0.0


async def _daily_loss_async(session) -> float:
    cutoff = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    result = await session.scalar(
        select(func.sum(SignalOutcome.pnl_pct)).where(SignalOutcome.closed_at >= cutoff)
    )
    return float(result or 0.0)


async def _monthly_drawdown_async(session) -> float:
    cutoff = datetime.utcnow() - timedelta(days=30)
    result = await session.execute(
        select(SignalOutcome.pnl_pct)
        .where(SignalOutcome.closed_at >= cutoff)
        .order_by(SignalOutcome.closed_at.asc())
    )
    pnls = [float(row[0]) for row in result.fetchall() if row[0] is not None]
    if not pnls:
        return 0.0

    equity = 1.0
    peak = equity
    max_drawdown = 0.0
    for pnl in pnls:
        equity *= 1.0 + pnl
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
    return max_drawdown


def notify_owner(msg: str) -> None:
    """Send an owner alert through Telegram."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("No TELEGRAM_BOT_TOKEN for notify_owner")
        return

    for owner_id in OWNER_IDS or []:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": owner_id, "text": msg}, timeout=5)
            logger.info("Notified owner %s: %s", owner_id, msg)
        except Exception:
            logger.exception("Failed to notify owner %s", owner_id)


def evaluate_system_health() -> bool:
    """Check limits and halt signal processing when a limit is exceeded."""
    try:
        async def check() -> bool:
            async with get_session() as session:
                dl = await _daily_loss_async(session)
                mdd = await _monthly_drawdown_async(session)
                if dl > MAX_DAILY_LOSS:
                    halt_system(f"Daily loss exceeded: {dl:.1%}")
                    return False
                if mdd > MAX_MONTHLY_DRAWDOWN:
                    halt_system(f"Monthly drawdown exceeded: {mdd:.1%}")
                    return False
                return True

        from utils.async_runner import run_sync

        return bool(run_sync(check()))
    except Exception:
        logger.exception("Health check failed")
        return True


def halt_system(reason: str) -> None:
    """Halt local signal processing and notify owners."""
    global SYSTEM_ACTIVE
    SYSTEM_ACTIVE = False
    msg = f"AUTO-KILL ACTIVATED: {reason}\nSystem halted globally."
    notify_owner(msg)
    logger.critical(msg)


def is_system_halted() -> bool:
    """Return whether the auto-kill switch has halted this process."""
    return not SYSTEM_ACTIVE


if __name__ == "__main__":
    evaluate_system_health()
