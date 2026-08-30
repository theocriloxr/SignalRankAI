"""Compatibility facade for the canonical PostgreSQL referral service.

Referral rewards are granted when a genuinely new user is attributed through a
stored referral code. First-purchase conversion is tracked separately and never
runs a second reward policy.
"""
from __future__ import annotations

import logging
from typing import Tuple

from sqlalchemy import func, select

from db.models import ReferralAttribution, ReferralReward, User
from db.session import get_session
from utils.timeutils import now_utc_naive

logger = logging.getLogger(__name__)


class ReferralManager:
    """Backward-compatible API backed by the canonical referral tables."""

    REFS_FOR_REWARD = 3
    REWARD_DAYS = 7

    async def get_referral_count(self, user_id: int) -> int:
        """Return lifetime qualified referrals for an internal users.id."""
        try:
            async with get_session(
                priority="interactive",
                label="referral_manager.count",
                timeout_seconds=8.0,
            ) as session:
                total = (
                    await session.execute(
                        select(func.count(ReferralAttribution.id)).where(
                            ReferralAttribution.referrer_user_id == int(user_id)
                        )
                    )
                ).scalar()
                return int(total or 0)
        except Exception as exc:
            logger.exception("[referral_manager_count_failed] user_id=%s error=%s", user_id, exc)
            return 0

    async def check_and_apply_reward(self, referrer_id: int) -> Tuple[bool, str]:
        """Report canonical reward status; signup processing applies rewards.

        This method intentionally does not mutate subscriptions. Keeping reward
        mutation in one code path prevents duplicate grants and conflicting
        signup-vs-purchase definitions.
        """
        try:
            async with get_session(
                priority="interactive",
                label="referral_manager.reward_status",
                timeout_seconds=8.0,
            ) as session:
                count = int(
                    (
                        await session.execute(
                            select(func.count(ReferralAttribution.id)).where(
                                ReferralAttribution.referrer_user_id == int(referrer_id)
                            )
                        )
                    ).scalar()
                    or 0
                )
                days = int(
                    (
                        await session.execute(
                            select(func.coalesce(func.sum(ReferralReward.reward_value), 0)).where(
                                ReferralReward.referrer_user_id == int(referrer_id),
                                ReferralReward.reward_type == "premium_days",
                            )
                        )
                    ).scalar()
                    or 0
                )
                return days > 0, f"{count} referrals; {days} premium days granted"
        except Exception as exc:
            logger.exception(
                "[referral_manager_reward_status_failed] referrer_id=%s error=%s",
                referrer_id,
                exc,
            )
            return False, f"Error: {type(exc).__name__}"

    async def record_referral(
        self,
        referrer_id: int,
        referred_user_id: int,
        is_successful: bool = False,
    ) -> bool:
        """Legacy internal-id helper with duplicate and self-referral guards."""
        if int(referrer_id) == int(referred_user_id):
            return False
        try:
            async with get_session(
                priority="interactive",
                label="referral_manager.record",
                timeout_seconds=8.0,
            ) as session:
                existing = (
                    await session.execute(
                        select(ReferralAttribution).where(
                            ReferralAttribution.referred_user_id == int(referred_user_id)
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    return int(existing.referrer_user_id) == int(referrer_id)
                session.add(
                    ReferralAttribution(
                        referrer_user_id=int(referrer_id),
                        referred_user_id=int(referred_user_id),
                        is_successful=bool(is_successful),
                        successful_at=now_utc_naive() if is_successful else None,
                        reward_applied=False,
                    )
                )
                await session.commit()
                return True
        except Exception as exc:
            logger.exception(
                "[referral_manager_record_failed] referrer_id=%s referred_user_id=%s error=%s",
                referrer_id,
                referred_user_id,
                exc,
            )
            return False

    async def mark_referral_successful(self, referred_user_id: int) -> bool:
        """Legacy internal-id conversion marker; no reward mutation occurs."""
        try:
            async with get_session(
                priority="interactive",
                label="referral_manager.mark_conversion",
                timeout_seconds=8.0,
            ) as session:
                referral = (
                    await session.execute(
                        select(ReferralAttribution)
                        .where(ReferralAttribution.referred_user_id == int(referred_user_id))
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                if referral is None:
                    return False
                referral.is_successful = True
                referral.successful_at = referral.successful_at or now_utc_naive()
                await session.commit()
                return True
        except Exception as exc:
            logger.exception(
                "[referral_manager_mark_failed] referred_user_id=%s error=%s",
                referred_user_id,
                exc,
            )
            return False

    async def mark_referral_conversion_by_telegram_id(
        self,
        telegram_user_id: int,
        payment_reference: str,
    ) -> bool:
        """Compatibility wrapper for payment integrations using Telegram IDs."""
        try:
            from db.pg_features import record_referral_conversion

            async with get_session(
                priority="critical",
                label="referral_manager.payment_conversion",
                timeout_seconds=10.0,
            ) as session:
                result = await record_referral_conversion(
                    session,
                    referred_telegram_user_id=int(telegram_user_id),
                    payment_reference=str(payment_reference),
                )
                await session.commit()
                return bool(result.get("recorded"))
        except Exception as exc:
            logger.exception(
                "[referral_manager_payment_conversion_failed] telegram_user_id=%s error=%s",
                telegram_user_id,
                exc,
            )
            return False
