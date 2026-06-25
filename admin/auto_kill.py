#!/usr/bin/env python3
\"\"\"Real auto-kill switch: monitors daily loss and monthly drawdown from DB outcomes.
Blocks new signals + notifies OWNER via Telegram if limits hit.

Limits:
- MAX_DAILY_LOSS=5% (sum pnl_pct signals closed today)
- MAX_MONTHLY_DRAWDOWN=20% (peak equity - current equity from signals)

Real-time: Queries SignalOutcome table.
Fail-open: Logs warnings if DB down.
\"\"\"

import os
import logging
from datetime import datetime, timedelta
from typing import Optional
import requests  # for Telegram API

from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from config import OWNER_IDS  # list of Telegram owner IDs
from core.tier_constants import DD_HARD_LIMIT  # or env
from db.session import get_session
from db.models import SignalOutcome  # assumes exists (pnl_pct, closed_at)

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()

MAX_DAILY_LOSS = float(os.getenv('MAX_DAILY_LOSS', '0.05'))  # 5%
MAX_MONTHLY_DRAWDOWN = float(os.getenv('MAX_MONTHLY_DRAWDOWN', '0.20'))  # 20%

SYSTEM_ACTIVE = True

def daily_loss(session: Session) -> float:
    \"\"\"Sum pnl_pct of signals closed today (UTC).\"\"\"  
    try:
        cutoff = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        total = session.query(func.sum(SignalOutcome.pnl_pct)).filter(
            SignalOutcome.closed_at >= cutoff
        ).scalar() or 0.0
        return total
    except Exception:
        logger.error(\"daily_loss query failed\")
        return 0.0

def monthly_drawdown(session: Session) -> float:
    \"\"\"Rolling monthly max DD: (peak_pnl - current_pnl) / peak_pnl.\"\"\"
    try:
        cutoff = datetime.utcnow() - timedelta(days=30)
        outcomes = session.query(SignalOutcome).filter(
            SignalOutcome.closed_at >= cutoff
        ).all()
        if not outcomes:
            return 0.0
        pnls = [o.pnl_pct for o in outcomes if o.pnl_pct is not None]
        if not pnls:
            return 0.0
        peak = max(pnls)
        current = sum(pnls[-10:])  # recent for 'current'
        if peak <= 0:
            return 0.0
        return max(0, (peak - current) / peak)
    except Exception:
        logger.error(\"monthly_drawdown query failed\")
        return 0.0

def notify_owner(msg: str) -> None:
    \"\"\"Send to all OWNER_IDS via Telegram.\"\"\"
    if not TELEGRAM_BOT_TOKEN:
        logger.warning(\"No TELEGRAM_BOT_TOKEN for notify_owner\")
        return
    for owner_id in OWNER_IDS or []:
        try:
            url = f\"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage\"
            requests.post(url, json={'chat_id': owner_id, 'text': msg}, timeout=5)
            logger.info(f\"Notified owner {owner_id}: {msg}\")
        except Exception as e:
            logger.error(f\"Failed to notify owner {owner_id}: {e}\")

def evaluate_system_health() -> bool:
    \"\"\"Check limits; halt if exceeded.\"\"\"
    global SYSTEM_ACTIVE
    try:
        async def check():
            async with get_session() as session:
                dl = daily_loss(session)
                mdd = monthly_drawdown(session)
                if dl > MAX_DAILY_LOSS:
                    reason = f\"Daily loss exceeded: {dl:.1%}\"
                    halt_system(reason)
                    return False
                if mdd > MAX_MONTHLY_DRAWDOWN:
                    reason = f\"Monthly drawdown exceeded: {mdd:.1%}\"
                    halt_system(reason)
                    return False
                return True
        from utils.async_runner import run_sync
        return run_sync(check())
    except Exception:
        logger.error(\"Health check failed\")
        return True  # fail-open

def halt_system(reason: str) -> None:
    \"\"\"Halt: set global flag + notify.\"\"\"
    global SYSTEM_ACTIVE
    SYSTEM_ACTIVE = False
    msg = f\"🚨 AUTO-KILL ACTIVATED: {reason}\\nSystem halted globally.\"
    notify_owner(msg)
    logger.critical(msg)

# Hook for engine: check before signal processing
def is_system_halted() -> bool:
    return not SYSTEM_ACTIVE

if __name__ == '__main__':
    # Test/run once
    evaluate_system_health()

