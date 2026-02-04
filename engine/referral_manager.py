"""
Referral reward system: 3 successful referrals = 7-day premium upgrade.
"""
import logging
from datetime import datetime, timedelta
from typing import Tuple, bool
from db.models import User, Referral
from db.session import async_session
from sqlalchemy import select, func

logger = logging.getLogger(__name__)

class ReferralManager:
    """Manage referral rewards and tier upgrades."""
    
    REFS_FOR_REWARD = 3
    REWARD_DAYS = 7
    
    async def get_referral_count(self, user_id: int) -> int:
        """Get successful referral count for user."""
        try:
            async with async_session() as session:
                stmt = select(func.count(Referral.id)).where(
                    Referral.referrer_id == user_id,
                    Referral.is_successful == True
                )
                result = await session.execute(stmt)
                return result.scalar() or 0
        except Exception as e:
            logger.error(f"Failed to get referral count: {e}")
            return 0
    
    async def check_and_apply_reward(self, referrer_id: int) -> Tuple[bool, str]:
        """
        Check if referrer reached reward threshold.
        If yes, apply 7-day premium upgrade and reset count.
        Returns (applied: bool, message: str)
        """
        try:
            async with async_session() as session:
                # Get current referral count
                stmt = select(func.count(Referral.id)).where(
                    Referral.referrer_id == referrer_id,
                    Referral.is_successful == True,
                    Referral.reward_applied == False
                )
                result = await session.execute(stmt)
                count = result.scalar() or 0
                
                if count < self.REFS_FOR_REWARD:
                    return False, f"{count}/{self.REFS_FOR_REWARD} referrals"
                
                # Get user
                user_stmt = select(User).where(User.id == referrer_id)
                user_result = await session.execute(user_stmt)
                user = user_result.scalars().first()
                
                if not user:
                    return False, "User not found"
                
                # Apply reward: upgrade tier if needed, extend premium
                now = datetime.utcnow()
                
                if user.tier == 'free':
                    # Free → Premium
                    user.tier = 'premium'
                    user.premium_until = now + timedelta(days=self.REWARD_DAYS)
                elif user.tier in ('premium', 'vip'):
                    # Extend existing premium/VIP
                    if user.premium_until is None or user.premium_until < now:
                        user.premium_until = now + timedelta(days=self.REWARD_DAYS)
                    else:
                        user.premium_until += timedelta(days=self.REWARD_DAYS)
                
                # Mark reward as applied
                ref_stmt = select(Referral).where(
                    Referral.referrer_id == referrer_id,
                    Referral.is_successful == True,
                    Referral.reward_applied == False
                ).limit(self.REFS_FOR_REWARD)
                
                ref_result = await session.execute(ref_stmt)
                refs = ref_result.scalars().all()
                
                for ref in refs:
                    ref.reward_applied = True
                
                await session.flush()
                
                msg = f"✅ Reward applied! Tier: {user.tier}, Premium until: {user.premium_until}"
                logger.info(f"Referral reward applied to user {referrer_id}: {msg}")
                
                return True, msg
        
        except Exception as e:
            logger.error(f"Failed to apply referral reward: {e}")
            return False, f"Error: {str(e)}"
    
    async def record_referral(self, referrer_id: int, referred_user_id: int, is_successful: bool = False) -> bool:
        """Record a referral relationship."""
        try:
            async with async_session() as session:
                referral = Referral(
                    referrer_id=referrer_id,
                    referred_user_id=referred_user_id,
                    is_successful=is_successful,
                    reward_applied=False,
                    created_at=datetime.utcnow()
                )
                
                session.add(referral)
                await session.flush()
                logger.info(f"Referral recorded: {referrer_id} → {referred_user_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to record referral: {e}")
            return False
    
    async def mark_referral_successful(self, referred_user_id: int) -> bool:
        """Mark a referral as successful when referred user makes first purchase."""
        try:
            async with async_session() as session:
                stmt = select(Referral).where(
                    Referral.referred_user_id == referred_user_id,
                    Referral.is_successful == False
                ).order_by(Referral.created_at.desc()).limit(1)
                
                result = await session.execute(stmt)
                referral = result.scalars().first()
                
                if referral:
                    referral.is_successful = True
                    referral.successful_at = datetime.utcnow()
                    await session.flush()
                    
                    logger.info(f"Referral marked successful: {referral.referrer_id} → {referred_user_id}")
                    return True
                
                return False
        except Exception as e:
            logger.error(f"Failed to mark referral successful: {e}")
            return False
