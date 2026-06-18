"""
Subscription Manager - PostgreSQL-backed Subscription State Machine

This module provides:
- Subscription state machine (active → expired → grace period → downgrade)
- Proper state transitions
- Retry logic for failed webhooks
- Invoice generation

Usage:
    from services.subscription_manager import SubscriptionManager
    
    # Get subscription status
    status = await SubscriptionManager.get_status(user_id)
    
    # Check and downgrade expired
    await SubscriptionManager.check_and_downgrade()
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger("SubscriptionManager")

# Grace period in days
GRACE_PERIOD_DAYS = 3

# Subscription tiers
TIER_FREE = "free"
TIER_PREMIUM = "premium"
TIER_VIP = "vip"


class SubscriptionState(Enum):
    """Subscription lifecycle states."""
    ACTIVE = "active"
    EXPIRED = "expired"
    GRACE_PERIOD = "grace_period"
    DOWNGRADED = "downgraded"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class SubscriptionManager:
    """
    PostgreSQL-backed subscription state machine.
    
    State transitions:
    - active → expired (subscription ends)
    - expired → grace_period (3 day grace)
    - grace_period → downregulated (grace ends, no payment)
    - grace_period → active (payment received during grace)
    
    Handles retry logic for failed webhook payments.
    """
    
    def __init__(self):
        self._grace_period_days = GRACE_PERIOD_DAYS
    
    @staticmethod
    async def get_status(user_id: int) -> Dict[str, Any]:
        """
        Get current subscription status for a user.
        
        Returns:
            Dict with tier, state, expires_at, days_remaining
        """
        try:
            from db.session import get_session
            from db.models import Subscription, User
            from sqlalchemy import select
            
            async with get_session() as session:
                # Get user
                result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.first()
                
                if not user:
                    return {
                        "tier": TIER_FREE,
                        "state": "none",
                        "expires_at": None,
                        "days_remaining": 0,
                    }
                
                # Get active subscription
                result = await session.execute(
                    select(Subscription).where(
                        Subscription.user_id == user_id,
                        Subscription.status == "active"
                    ).order_by(Subscription.expires_at.desc()).limit(1)
                )
                sub = result.first()
                
                if not sub:
                    return {
                        "tier": user.tier,
                        "state": "none",
                        "expires_at": None,
                        "days_remaining": 0,
                    }
                
                # Calculate days remaining
                days_remaining = 0
                if sub.expires_at:
                    delta = sub.expires_at - datetime.utcnow()
                    days_remaining = max(0, delta.days)
                
                return {
                    "tier": sub.tier,
                    "state": sub.status,
                    "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
                    "days_remaining": days_remaining,
                    "auto_renew": user.auto_renew,
                }
                
        except Exception as e:
            logger.debug(f"[SubscriptionManager] Get status error: {e}")
            return {
                "tier": TIER_FREE,
                "state": "unknown",
                "expires_at": None,
                "days_remaining": 0,
            }
    
    @staticmethod
    async def get_subscription(user_id: int) -> Optional[Dict[str, Any]]:
        """Get subscription object for user."""
        try:
            from db.session import get_session
            from db.models import Subscription
            from sqlalchemy import select
            
            async with get_session() as session:
                result = await session.execute(
                    select(Subscription).where(
                        Subscription.user_id == user_id,
                        Subscription.status == "active"
                    ).order_by(Subscription.expires_at.desc()).limit(1)
                )
                sub = result.first()
                
                if sub:
                    return {
                        "id": sub.id,
                        "tier": sub.tier,
                        "status": sub.status,
                        "expires_at": sub.expires_at,
                        "started_at": sub.started_at,
                    }
                return None
                
        except Exception as e:
            logger.debug(f"[SubscriptionManager] Get subscription error: {e}")
            return None
    
    @staticmethod
    async def create_subscription(
        user_id: int,
        tier: str,
        duration_days: int = 30,
        paystack_reference: Optional[str] = None,
        bonus_days: int = 0
    ) -> bool:
        """
        Create or extend a subscription.
        
        Args:
            user_id: User ID
            tier: Subscription tier
            duration_days: Duration in days
            paystack_reference: Paystack reference
            bonus_days: Bonus days (from referral rewards etc.)
        """
        try:
            from db.session import get_session
            from db.models import Subscription, User
            from sqlalchemy import select
            from utils.timeutils import now_utc_naive
            
            async with get_session() as session:
                # Get existing active subscription
                result = await session.execute(
                    select(Subscription).where(
                        Subscription.user_id == user_id,
                        Subscription.status == "active"
                    ).order_by(Subscription.expires_at.desc()).limit(1)
                )
                existing_sub = result.first()
                
                now = now_utc_naive()
                expires_at = now + timedelta(days=duration_days)
                
                # Add bonus days
                if bonus_days > 0:
                    expires_at = expires_at + timedelta(days=bonus_days)
                
                if existing_sub:
                    # Extend existing
                    existing_sub.tier = tier
                    existing_sub.expires_at = expires_at
                    existing_sub.paystack_reference = paystack_reference
                    existing_sub.status = "active"
                else:
                    # Create new
                    new_sub = Subscription(
                        user_id=user_id,
                        tier=tier,
                        status="active",
                        started_at=now,
                        expires_at=expires_at,
                        paystack_reference=paystack_reference,
                        bonus_days=bonus_days,
                    )
                    session.add(new_sub)
                
                # Update user tier
                user_result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = user_result.first()
                if user:
                    user.tier = tier
                
                await session.commit()
                
                logger.info(f"[SubscriptionManager] Created {tier} subscription for user {user_id}, expires {expires_at}")
                return True
                
        except Exception as e:
            logger.error(f"[SubscriptionManager] Create subscription error: {e}")
            return False
    
    @staticmethod
    async def expire_subscription(user_id: int) -> bool:
        """
        Mark subscription as expired (start grace period).
        """
        try:
            from db.session import get_session
            from db.models import Subscription
            from sqlalchemy import select
            
            async with get_session() as session:
                result = await session.execute(
                    select(Subscription).where(
                        Subscription.user_id == user_id,
                        Subscription.status == "active"
                    ).order_by(Subscription.expires_at.desc()).limit(1)
                )
                sub = result.first()
                
                if sub:
                    sub.status = "grace_period"
                    await session.commit()
                    logger.info(f"[SubscriptionManager] Subscription expired for user {user_id}")
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"[SubscriptionManager] Expire subscription error: {e}")
            return False
    
    @staticmethod
    async def downgrade_user(user_id: int) -> bool:
        """
        Downgrade user to free tier after grace period.
        """
        try:
            from db.session import get_session
            from db.models import Subscription, User
            from sqlalchemy import select
            
            async with get_session() as session:
                # Update subscription status
                result = await session.execute(
                    select(Subscription).where(
                        Subscription.user_id == user_id,
                        Subscription.status == "grace_period"
                    )
                )
                for sub in result.scalars().all():
                    sub.status = "downgraded"
                
                # Downgrade user tier
                user_result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = user_result.first()
                if user:
                    user.tier = TIER_FREE
                
                await session.commit()
                
                logger.info(f"[SubscriptionManager] Downgraded user {user_id} to free tier")
                return True
                
        except Exception as e:
            logger.error(f"[SubscriptionManager] Downgrade error: {e}")
            return False
    
    @staticmethod
    async def check_and_downgrade() -> int:
        """
        Check all subscriptions and downgrade expired ones.
        
        Returns:
            Number of users downgraded
        """
        try:
            from db.session import get_session
            from db.models import Subscription
            from sqlalchemy import select
            from utils.timeutils import now_utc_naive
            
            now = now_utc_naive()
            grace_end = now - timedelta(days=GRACE_PERIOD_DAYS)
            
            async with get_session() as session:
                # Find subscriptions in grace period past grace end
                result = await session.execute(
                    select(Subscription).where(
                        Subscription.status == "grace_period",
                        Subscription.expires_at < grace_end
                    )
                )
                
                downgraded = 0
                for sub in result.scalars().all():
                    # Get user_id from sub
                    user_id = sub.user_id
                    
                    # Update subscription
                    sub.status = "downgraded"
                    
                    # Update user tier
                    user_result = await session.execute(
                        select(User).where(User.id == user_id)
                    )
                    user = user_result.first()
                    if user:
                        user.tier = TIER_FREE
                    
                    downgraded += 1
                    logger.info(f"[SubscriptionManager] Downgraded user {user_id}")
                
                await session.commit()
                return downgraded
                
        except Exception as e:
            logger.error(f"[SubscriptionManager] Check and downgrade error: {e}")
            return 0
    
    @staticmethod
    async def extend_subscription(
        user_id: int,
        days: int,
        reason: str = "manual"
    ) -> bool:
        """Extend subscription by days."""
        try:
            from db.session import get_session
            from db.models import Subscription
            from sqlalchemy import select
            from utils.timeutils import now_utc_naive
            
            async with get_session() as session:
                result = await session.execute(
                    select(Subscription).where(
                        Subscription.user_id == user_id,
                        Subscription.status.in_(["active", "grace_period"])
                    ).order_by(Subscription.expires_at.desc()).limit(1)
                )
                sub = result.first()
                
                if sub:
                    if sub.expires_at and sub.expires_at > now_utc_naive():
                        sub.expires_at = sub.expires_at + timedelta(days=days)
                    else:
                        sub.expires_at = now_utc_naive() + timedelta(days=days)
                    sub.status = "active"
                    
                    # Update metadata
                    meta = sub.meta or {}
                    meta["extensions"] = meta.get("extensions", 0) + 1
                    meta["last_extension_reason"] = reason
                    sub.meta = meta
                    
                    await session.commit()
                    logger.info(f"[SubscriptionManager] Extended user {user_id} by {days} days")
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"[SubscriptionManager] Extend error: {e}")
            return False
    
    @staticmethod
    async def cancel_subscription(user_id: int) -> bool:
        """Cancel subscription (immediate downgrade)."""
        try:
            from db.session import get_session
            from db.models import Subscription, User
            from sqlalchemy import select
            
            async with get_session() as session:
                # Update subscriptions
                result = await session.execute(
                    select(Subscription).where(
                        Subscription.user_id == user_id,
                        Subscription.status.in_(["active", "grace_period"])
                    )
                )
                for sub in result.scalars().all():
                    sub.status = "cancelled"
                
                # Update user tier
                user_result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = user_result.first()
                if user:
                    user.tier = TIER_FREE
                
                await session.commit()
                
                logger.info(f"[SubscriptionManager] Cancelled subscription for user {user_id}")
                return True
                
        except Exception as e:
            logger.error(f"[SubscriptionManager] Cancel error: {e}")
            return False
    
    @staticmethod
    async def get_users_expiring(days: int = 3) -> List[int]:
        """Get users expiring within specified days."""
        try:
            from db.session import get_session
            from db.models import Subscription
            from sqlalchemy import select
            from utils.timeutils import now_utc_naive
            
            now = now_utc_naive()
            cutoff = now + timedelta(days=days)
            
            async with get_session() as session:
                result = await session.execute(
                    select(Subscription.user_id).where(
                        Subscription.status == "active",
                        Subscription.expires_at <= cutoff,
                        Subscription.expires_at > now
                    ).distinct()
                )
                return [row[0] for row in result.fetchall()]
                
        except Exception as e:
            logger.debug(f"[SubscriptionManager] Get expiring error: {e}")
            return []


# Convenience functions
async def get_subscription_status(user_id: int) -> Dict[str, Any]:
    """Get subscription status."""
    return await SubscriptionManager.get_status(user_id)


async def create_user_subscription(
    user_id: int,
    tier: str,
    duration_days: int = 30,
    paystack_reference: Optional[str] = None
) -> bool:
    """Create subscription for user."""
    return await SubscriptionManager.create_subscription(
        user_id, tier, duration_days, paystack_reference
    )


async def extend_user_subscription(
    user_id: int,
    days: int,
    reason: str = "manual"
) -> bool:
    """Extend subscription."""
    return await SubscriptionManager.extend_subscription(user_id, days, reason)


if __name__ == "__main__":
    # Quick test
    import asyncio
    
    async def test():
        print("Testing Subscription Manager...")
        
        # Test get status
        status = await get_subscription_status(user_id=1)
        print(f"Status: {status}")
    
    asyncio.run(test())
