"""Shared, fail-closed per-user broker execution quotas.

MT5 and Bybit draw from the same daily execution counter. The counter is
reserved before broker I/O and is released only for a definite rejection before
an order can exist. Ambiguous submissions remain reserved until reconciliation.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from sqlalchemy import func, select

from db.models import BrokerExecution, MT5Execution, User
from db.session import get_session

logger = logging.getLogger(__name__)


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def reserve_user_execution_quota(
    telegram_user_id: int,
    *,
    tier: str,
    execution_mode: str,
) -> tuple[bool, str, int | None]:
    """Reserve one shared daily execution slot under a row lock."""
    try:
        now = _now_naive()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        async with get_session(label="execution.quota.reserve", timeout_seconds=8.0) as session:
            user = (
                await session.execute(
                    select(User)
                    .where(User.telegram_user_id == int(telegram_user_id))
                    .with_for_update()
                    .limit(1)
                )
            ).scalar_one_or_none()
            if user is None:
                await session.rollback()
                return False, "user_profile_missing", None

            reset_at = getattr(user, "daily_executions_reset_at", None)
            if reset_at is None or reset_at.date() < now.date():
                user.daily_executions_today = 0
                user.daily_executions_reset_at = now

            mt5_realized = await session.execute(
                select(func.coalesce(func.sum(MT5Execution.realized_pnl_pct), 0.0)).where(
                    MT5Execution.user_id == int(user.id),
                    MT5Execution.executed_at >= day_start,
                )
            )
            bybit_realized = await session.execute(
                select(func.coalesce(func.sum(BrokerExecution.realized_pnl_pct), 0.0)).where(
                    BrokerExecution.user_id == int(user.id),
                    BrokerExecution.provider == "bybit",
                    BrokerExecution.closed_at >= day_start,
                )
            )
            pnl_today = float(mt5_realized.scalar_one_or_none() or 0.0) + float(
                bybit_realized.scalar_one_or_none() or 0.0
            )
            drawdown_cap = float(getattr(user, "max_daily_drawdown_pct", 8.0) or 8.0)
            if drawdown_cap > 0 and pnl_today <= -abs(drawdown_cap):
                await session.rollback()
                return False, "daily_drawdown_guard", int(user.id)

            current = int(getattr(user, "daily_executions_today", 0) or 0)
            tier_upper = str(tier or "FREE").upper()
            if tier_upper == "PREMIUM":
                limit = max(0, int(os.getenv("PREMIUM_DAILY_EXECUTIONS", "3") or 3))
                if limit == 0 or current >= limit:
                    await session.rollback()
                    return False, "premium_daily_execution_limit", int(user.id)

            mode = str(execution_mode or "").strip().lower()
            if mode in {"auto", "live"}:
                auto_limit = int(getattr(user, "auto_signals_daily_limit", 0) or 0)
                if auto_limit == 0:
                    await session.rollback()
                    return False, "auto_execution_limit_disabled", int(user.id)
                if auto_limit > 0 and current >= auto_limit:
                    await session.rollback()
                    return False, "auto_daily_execution_limit", int(user.id)

            user.daily_executions_today = current + 1
            user.daily_executions_reset_at = now
            await session.commit()
            return True, "", int(user.id)
    except Exception:
        logger.warning("shared execution quota unavailable; blocking", exc_info=True)
        return False, "execution_quota_unavailable", None


async def release_user_execution_quota(user_db_id: int | None) -> None:
    """Release a reservation only after a definite pre-order/provider rejection."""
    if not user_db_id:
        return
    try:
        async with get_session(label="execution.quota.release", timeout_seconds=8.0) as session:
            user = (
                await session.execute(
                    select(User).where(User.id == int(user_db_id)).with_for_update().limit(1)
                )
            ).scalar_one_or_none()
            if user is not None:
                user.daily_executions_today = max(
                    0, int(getattr(user, "daily_executions_today", 0) or 0) - 1
                )
            await session.commit()
    except Exception:
        logger.warning("failed to release execution quota; reconciliation required", exc_info=True)


__all__ = ["release_user_execution_quota", "reserve_user_execution_quota"]
