"""
Smart signal distribution with deduplication and rate-limiting.

Rules:
1. Never send the same signal twice to the same user (checked via SignalDelivery unique constraint)
2. Never exhaust a user's daily limit in one cycle (rate-limit per cycle)
3. Spread signals evenly across the day instead of front-loading
4. Track all delivery attempts for debugging and retry logic

Example:
    - FREE tier: 3 signals/day hard limit
    - If 5 signals generated in one cycle, only sample 1 per cycle (staggered)
    - PREMIUM: 10/day, sample max 2-3 per cycle
    - VIP: 20/day, sample max 5-7 per cycle

This ensures good user experience with even signal distribution.
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from db.models import SignalDelivery, User
from core.tier_constants import TIER_DAILY_LIMITS, TIER_SCORE_THRESHOLDS
from utils.timeutils import now_utc_naive

logger = logging.getLogger(__name__)

# Rate-limit: max signals to sample per USER per CYCLE
# This prevents exhausting daily limits in one go
SIGNALS_PER_USER_PER_CYCLE = {
    'free': 1,      # 1 signal per 30-sec cycle max
    'premium': 1,   # 2 signals per 30-sec cycle max
    'vip': 2,       # 3 signals per 30-sec cycle max
    'admin': 5,     # Admins get more in one cycle
    'owner': 10,    # Owners get many in one cycle
}


class SignalDistributor:
    """
    Distributes signals to users based on tier rules.
    
    Ensures:
    - No duplicate delivery (unique user_id + signal_id)
    - Daily limits not exhausted in single cycle
    - Random sampling without repeating to same user
    """
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_eligible_users_for_tier(
        self,
        tier: str,
        signal_id: str,
        limit: Optional[int] = None
    ) -> List[int]:
        """
        Get users eligible for this signal (by tier, excluding already-sent).
        
        Args:
            tier: User tier (free, premium, vip, admin, owner)
            signal_id: Signal ID to check for existing deliveries
            limit: Max users to return (for rate-limiting per cycle)
        
        Returns:
            List of user_ids eligible to receive this signal
        """
        # Get users of this tier who haven't received this signal yet
        eligible = self.session.query(User.id).filter(
            and_(
                User.tier == tier,
                User.accepted_terms == True,  # Terms must be accepted
            )
        ).outerjoin(
            SignalDelivery,
            and_(
                SignalDelivery.user_id == User.id,
                SignalDelivery.signal_id == signal_id,
            )
        ).filter(
            SignalDelivery.id == None  # No existing delivery for this user+signal
        ).all()
        
        user_ids = [u[0] for u in eligible]
        
        if limit:
            # Randomly select subset (respect per-cycle rate limit)
            import random
            user_ids = random.sample(user_ids, min(len(user_ids), limit))
        
        return user_ids
    
    def count_delivered_signals_today(
        self,
        user_id: int,
        user_local_timezone: Optional[str] = None
    ) -> int:
        """
        Count how many signals have been DELIVERED (sent_ok=True) to user today.
        
        Uses user's local timezone for day boundary (or UTC if not specified).
        
        Args:
            user_id: User ID
            user_local_timezone: User's local timezone (e.g., 'Africa/Lagos')
        
        Returns:
            Count of delivered signals today
        """
        # For now, use UTC. In future, use user_local_timezone
        # to respect their local midnight (not UTC midnight)
        
        today_start = now_utc_naive().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start.replace(hour=23, minute=59, second=59)
        
        count = self.session.query(func.count(SignalDelivery.id)).filter(
            and_(
                SignalDelivery.user_id == user_id,
                SignalDelivery.sent_ok == True,  # Only count successful deliveries
                SignalDelivery.delivered_at >= today_start,
                SignalDelivery.delivered_at <= today_end,
            )
        ).scalar() or 0
        
        return count
    
    def can_receive_signal(
        self,
        user_id: int,
        tier: str,
        signal_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if user can receive this signal (not duplicate, within daily limit).
        
        Args:
            user_id: User ID
            tier: User's tier
            signal_id: Signal to send
        
        Returns:
            (can_send: bool, reason: str or None if OK)
        """
        # Check 1: Already delivered?
        already_sent = self.session.query(SignalDelivery).filter(
            and_(
                SignalDelivery.user_id == user_id,
                SignalDelivery.signal_id == signal_id,
            )
        ).first()
        
        if already_sent:
            return False, f"Signal {signal_id[:8]} already sent to user"
        
        # Check 2: Daily limit exceeded?
        daily_limit = TIER_DAILY_LIMITS.get(tier.lower(), 3)
        delivered_today = self.count_delivered_signals_today(user_id)
        
        if delivered_today >= daily_limit:
            return False, f"User hit daily limit ({delivered_today}/{daily_limit})"
        
        return True, None
    
    def sample_users_for_signal(
        self,
        signal: Dict,
        signal_id: str
    ) -> Dict[str, List[int]]:
        """
        Sample random users per tier for this signal.
        
        Respects:
        - Quality score thresholds (gate by tier)
        - Per-cycle rate limits (don't exhaust daily limit in one cycle)
        - No duplicates (check SignalDelivery for user+signal)
        - Daily limits per user
        
        Args:
            signal: Signal dict with 'score' field
            signal_id: Signal ID
        
        Returns:
            Dict: {'free': [user_ids], 'premium': [user_ids], 'vip': [user_ids], ...}
        """
        score = float(signal.get('score', 0) or 0)
        
        result = {
            'free': [],
            'premium': [],
            'vip': [],
            'admin': [],
            'owner': [],
        }
        
        # Determine eligible tiers by score threshold
        for tier in result.keys():
            threshold = TIER_SCORE_THRESHOLDS.get(tier, 85)
            if score < threshold and tier not in ('admin', 'owner'):
                # This tier doesn't qualify (except admins/owners always get)
                continue
            
            # Get eligible users for this tier (respecting per-cycle limit)
            per_cycle_limit = SIGNALS_PER_USER_PER_CYCLE.get(tier, 1)
            eligible_users = self.get_eligible_users_for_tier(
                tier, 
                signal_id,
                limit=per_cycle_limit
            )
            
            # Further filter by daily limit per user
            users_with_room = []
            for user_id in eligible_users:
                can_send, _ = self.can_receive_signal(user_id, tier, signal_id)
                if can_send:
                    users_with_room.append(user_id)
            
            result[tier] = users_with_room
            
            if users_with_room:
                logger.info(
                    f"Sampled {len(users_with_room)} {tier} users for signal {signal_id[:8]} "
                    f"(score {score}, threshold {threshold})"
                )
        
        return result
    
    def record_delivery_attempt(
        self,
        user_id: int,
        signal_id: str,
        tier: str,
        sent_ok: bool,
        error: Optional[str] = None
    ) -> SignalDelivery:
        """
        Record that we attempted to send a signal to a user.
        
        This creates the (user_id, signal_id) pair in SignalDelivery,
        which prevents re-delivery due to unique constraint.
        
        Args:
            user_id: User ID
            signal_id: Signal ID
            tier: User's tier at time of send
            sent_ok: True if delivery succeeded (Telegram API accepted)
            error: Error message if send failed
        
        Returns:
            SignalDelivery record created
        """
        delivery = SignalDelivery(
            user_id=user_id,
            signal_id=signal_id,
            tier_at_send=tier,
            sent_ok=sent_ok,
            attempt_count=1,
            last_attempt_at=now_utc_naive(),
            last_error=error,
        )
        self.session.add(delivery)
        self.session.commit()
        
        if error:
            logger.warning(
                f"Failed to deliver signal {signal_id[:8]} to user {user_id}: {error}"
            )
        else:
            logger.info(f"Delivered signal {signal_id[:8]} to user {user_id} ({tier})")
        
        return delivery
    
    def get_delivery_status(
        self,
        user_id: int,
        signal_id: str
    ) -> Optional[SignalDelivery]:
        """
        Check if signal was delivered to user and get delivery record.
        
        Args:
            user_id: User ID
            signal_id: Signal ID
        
        Returns:
            SignalDelivery record or None
        """
        return self.session.query(SignalDelivery).filter(
            and_(
                SignalDelivery.user_id == user_id,
                SignalDelivery.signal_id == signal_id,
            )
        ).first()


def create_distributor(session: Session) -> SignalDistributor:
    """Factory function to create a SignalDistributor."""
    return SignalDistributor(session)
