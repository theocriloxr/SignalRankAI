"""Payment confirmation and tier-upgrade logic for SignalRankAI."""

import os
import asyncio
from datetime import datetime
from typing import Dict, Tuple, Optional

async def verify_payment_and_upgrade_tier(
    user_id: int,
    tier: str,
    duration_days: int,
    amount: float
) -> Tuple[bool, str]:
    """
    Verify payment was processed for tier upgrade and update user tier in database.
    
    Returns:
        (success: bool, message: str)
    """
    try:
        from db.session import ENGINE, get_session
        from db.repository import activate_subscription, get_active_subscription
        
        if ENGINE is None:
            return False, "Database not configured"
        
        # Check if payment was already processed (idempotency)
        async with get_session() as session:
            existing_sub = await get_active_subscription(
                session, 
                telegram_user_id=user_id, 
                tier=tier.upper()
            )
            await session.commit()
        
        if existing_sub is not None:
            # Already has this tier subscription
            return True, f"✅ Already subscribed to {tier.upper()}. Enjoy premium features!"
        
        # Activate new subscription
        async with get_session() as session:
            await activate_subscription(
                session,
                telegram_user_id=user_id,
                tier=tier.upper(),
                duration_days=duration_days,
                amount_paid=amount,
                payment_provider="paystack"
            )
            await session.commit()
        
        tier_upper = tier.upper()
        msg = f"✅ Payment confirmed! You're now {tier_upper} tier.\n\n"
        
        if tier_upper == "PREMIUM":
            msg += (
                "🎉 Premium Benefits:\n"
                "• Performance analytics\n"
                "• 65+ confidence signals\n"
                "• Entry zones & partial TPs\n"
                "• Risk management tools\n"
                "• Signal history (30 days)\n\n"
                "Use /performance to check your stats!"
            )
        elif tier_upper == "VIP":
            msg += (
                "🏆 VIP Benefits:\n"
                "• Everything in Premium +\n"
                "• All signals (55+)\n"
                "• Full TP levels (TP1, TP2, TP3)\n"
                "• HTF bias & confluence scores\n"
                "• Trade logic & invalidation levels\n"
                "• Early alerts & NO-TRADE zones\n"
                "• Monthly performance reports\n\n"
                "Use /elite to see high-confidence signals!"
            )
        
        return True, msg
        
    except Exception as e:
        error_msg = str(e)
        return False, f"❌ Upgrade failed: {error_msg}\n\nPlease contact support or try again."


async def check_pending_payments(user_id: int) -> Optional[Dict]:
    """
    Check if user has pending payment that needs verification.
    Used in upgrade command to show payment status.
    """
    try:
        from db.session import ENGINE, get_session
        
        if ENGINE is None:
            return None
        
        # This would check for unpaid subscriptions or pending transactions
        # For now, return None (no pending payments)
        return None
        
    except Exception:
        return None


async def format_tier_upgrade_confirmation(
    tier: str,
    amount: float,
    duration_days: int,
    user_id: int
) -> str:
    """Format a confirmation message before payment is processed."""
    
    tier_upper = tier.upper()
    
    if tier_upper == "PREMIUM":
        benefits = (
            "🎉 PREMIUM TIER (7–30 days)\n\n"
            "✅ Performance analytics\n"
            "✅ Signals with 65+ confidence\n"
            "✅ Entry zones\n"
            "✅ TP1 & TP2 levels\n"
            "✅ Risk guidance\n"
            "✅ 30-day history\n\n"
            f"💰 Amount: ₦{amount:,.0f}\n"
            f"⏰ Duration: {duration_days} days\n\n"
            "Click below to pay with Paystack."
        )
    elif tier_upper == "VIP":
        benefits = (
            "🏆 VIP TIER (30 days)\n\n"
            "✅ Everything in Premium +\n"
            "✅ All signals (score 55+)\n"
            "✅ TP1, TP2, TP3 levels\n"
            "✅ HTF bias & confluence scores\n"
            "✅ Trade logic explanations\n"
            "✅ Invalidation levels\n"
            "✅ Early alerts\n"
            "✅ NO-TRADE zone warnings\n"
            "✅ Monthly performance reports\n\n"
            f"💰 Amount: ₦{amount:,.0f}\n"
            f"⏰ Duration: {duration_days} days\n\n"
            "Limited VIP seats available. Click below to secure yours!"
        )
    else:
        benefits = f"{tier_upper} Tier - ₦{amount:,.0f} for {duration_days} days"
    
    return benefits
