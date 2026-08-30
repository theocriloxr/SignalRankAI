"""Best-effort, non-blocking upgrade-intent analytics."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.tier_policy import AccessDecision

logger = logging.getLogger(__name__)


def build_upgrade_intent_event(
    decision: AccessDecision,
    *,
    action: str,
    source: str,
) -> dict[str, Any]:
    return decision.intent_payload(action=action, source=source)


async def record_upgrade_intent(
    telegram_user_id: int,
    decision: AccessDecision,
    *,
    action: str,
    source: str,
) -> bool:
    """Persist a denied product action without delaying the user response."""
    if decision.allowed or decision.code != "TIER_LOCKED":
        return False
    try:
        from db.models import BotEvent, User
        from db.priority import DBPriority
        from db.session import get_session
        from sqlalchemy import select

        async with get_session(priority=DBPriority.ANALYTICS) as session:
            user = (
                await session.execute(
                    select(User).where(User.telegram_user_id == int(telegram_user_id)).limit(1)
                )
            ).scalar_one_or_none()
            if user is None:
                return False
            session.add(
                BotEvent(
                    user_id=int(user.id),
                    event_type="upgrade_intent",
                    meta=build_upgrade_intent_event(decision, action=action, source=source),
                )
            )
            await session.commit()
            return True
    except Exception as exc:
        logger.debug("[upgrade_intent] deferred/dropped action=%s error=%s", action, exc)
        return False


def schedule_upgrade_intent(
    telegram_user_id: int,
    decision: AccessDecision,
    *,
    action: str,
    source: str,
) -> asyncio.Task[bool] | None:
    if decision.allowed or decision.code != "TIER_LOCKED":
        return None
    try:
        task = asyncio.create_task(
            record_upgrade_intent(
                int(telegram_user_id),
                decision,
                action=action,
                source=source,
            ),
            name=f"upgrade_intent:{str(action)[:32]}",
        )
        return task
    except RuntimeError:
        return None


__all__ = [
    "build_upgrade_intent_event",
    "record_upgrade_intent",
    "schedule_upgrade_intent",
]
