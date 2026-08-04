"""Payment confirmation and tier-upgrade logic for SignalRankAI."""

import os
import asyncio
import logging
from datetime import datetime
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)


async def subscription_checkout_callback(update, context) -> None:
    """Handle ``subscribe:<plan_code>`` plan-selection callbacks.

    Exactly one Paystack transaction is initialized per tap. The callback is
    acknowledged immediately, the plan is validated against the server-side
    catalogue, and every outcome (success or failure) is surfaced as a visible
    Telegram message — never only via ``query.answer()``.
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    query = getattr(update, "callback_query", None)
    if query is None:
        return
    data = str(getattr(query, "data", "") or "")
    if not data.startswith("subscribe:"):
        return

    user = getattr(update, "effective_user", None)
    telegram_user_id = int(user.id) if user is not None else None
    logger.info(
        "[payment_callback_received] user=%s data=%s",
        telegram_user_id,
        data[:64],
    )

    plan_code = data.split(":", 1)[1].strip().lower() if ":" in data else ""
    from payments.plan_catalogue import get_plan

    plan = get_plan(plan_code)
    if plan is None:
        try:
            await query.answer("Unknown plan. Please open /upgrade again.", show_alert=True)
        except Exception:
            pass
        try:
            if query.message is not None:
                await query.message.reply_text(
                    "❌ That plan is no longer available. Please open /upgrade to see current plans."
                )
        except Exception:
            pass
        return
    logger.info("[payment_plan_validated] user=%s plan=%s", telegram_user_id, plan.code)

    if telegram_user_id is None:
        try:
            await query.answer("Could not identify your Telegram account.", show_alert=True)
        except Exception:
            pass
        return

    # Immediate acknowledgement — the bot must answer callbacks quickly.
    try:
        await query.answer()
    except Exception:
        pass

    # VIP seat capacity gate.
    if plan.tier == "VIP":
        try:
            from signalrank_telegram.commands import _get_live_vip_seat_state

            _, _, vip_sold_out = await _get_live_vip_seat_state()
            if vip_sold_out:
                text = (
                    "💎 VIP is currently sold out.\n\n"
                    "Join the waitlist with /upgrade and we will notify you when a seat opens."
                )
                try:
                    if query.message is not None:
                        await query.message.reply_text(text)
                except Exception:
                    pass
                return
        except Exception as exc:
            logger.debug("[vip_capacity_check_failed] %s", type(exc).__name__)

    # Existing entitlement check — avoid selling what the user already has.
    try:
        from db.repository import get_active_subscription
        from db.session import get_session

        async with get_session(label="paystack.eligibility", timeout_seconds=8.0) as session:
            existing = await get_active_subscription(
                session, telegram_user_id=int(telegram_user_id), tier=plan.tier
            )
            await session.commit()
        if existing is not None:
            expiry = getattr(existing, "expires_at", None)
            expiry_text = (
                expiry.strftime("%Y-%m-%d") if hasattr(expiry, "strftime") else "active"
            )
            text = (
                f"✅ You already have an active {plan.tier} subscription until {expiry_text}.\n"
                "No need to pay again — use /status to check your account."
            )
            try:
                if query.message is not None:
                    await query.message.reply_text(text)
            except Exception:
                pass
            return
    except Exception as exc:
        logger.debug("[subscription_eligibility_check_failed] %s", type(exc).__name__)

    # Real saved email when available.
    email: str | None = None
    try:
        from db.session import get_session
        from db.repository import get_or_create_user

        async with get_session(label="paystack.email_resolve", timeout_seconds=8.0) as session:
            user_row = await get_or_create_user(session, telegram_user_id=int(telegram_user_id))
            email = getattr(user_row, "email", None) or None
            await session.commit()
    except Exception:
        email = None

    from paystack.paystack import initialize_paystack_checkout

    result = await initialize_paystack_checkout(
        int(telegram_user_id),
        plan.code,
        email=email,
    )
    if not result.ok:
        logger.warning(
            "[paystack_checkout_failed] user=%s plan=%s mode=%s reason=%s",
            telegram_user_id, plan.code, result.mode, result.reason,
        )
        text = (
            "❌ Checkout could not be started right now.\n\n"
            "Please try again in a moment, or contact Support: @theocrilox."
        )
        try:
            if query.message is not None:
                await query.message.reply_text(text)
        except Exception:
            pass
        return

    if not result.authorization_url:
        logger.error(
            "[paystack_checkout_failed] missing_url user=%s plan=%s",
            telegram_user_id, plan.code,
        )
        try:
            if query.message is not None:
                await query.message.reply_text(
                    "❌ The payment provider returned an invalid checkout link. "
                    "Please contact Support: @theocrilox."
                )
        except Exception:
            pass
        return

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("💳 Continue to Paystack", url=result.authorization_url),
    ]])
    text = (
        f"🚀 <b>{plan.label} checkout ready</b>\n\n"
        f"• Plan: {plan.label}\n"
        f"• Amount: ₦{plan.price_ngn:,} (NGN)\n"
        f"• Duration: {plan.duration_days} days\n\n"
        "Tap <b>Continue to Paystack</b> to complete your payment. "
        "Your subscription activates automatically once payment is confirmed."
    )
    try:
        if query.message is not None:
            await query.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        pass
    logger.info(
        "[paystack_checkout_initialized] user=%s plan=%s reference=%s mode=%s",
        telegram_user_id, plan.code, result.reference, result.mode,
    )


async def handle_subscription_callback_fallback(update, context) -> None:
    """Defensive fallback: subscription callbacks must never 404 silently."""
    query = getattr(update, "callback_query", None)
    if query is None:
        return
    data = str(getattr(query, "data", "") or "")
    if not data.startswith("subscribe:"):
        return
    try:
        await query.answer()
    except Exception:
        pass
    try:
        if query.message is not None:
            await query.message.reply_text(
                "This payment button is outdated. Please send /upgrade to get fresh checkout buttons."
            )
    except Exception:
        pass

async def verify_payment_and_upgrade_tier(
    user_id: int,
    tier: str,
    duration_days: int,
    amount: float,
    paystack_reference: str | None = None,
) -> Tuple[bool, str]:
    """
    Verify payment was processed for tier upgrade and update user tier in database.
    
    Returns:
        (success: bool, message: str)
    """
    try:
        reference = str(paystack_reference or "").strip()
        if not reference:
            return False, "A verified Paystack reference is required."
        from payments.paystack import verify_payment
        if not await verify_payment(reference, float(amount)):
            return False, "Paystack could not verify this transaction."
        from db.session import get_engine_for_event_loop, get_session
        from db.repository import activate_subscription, get_active_subscription
        engine = get_engine_for_event_loop()
        if engine is None:
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
                paystack_reference=reference,
                meta={"provider": "paystack", "legacy_verified_helper": True, "amount_ngn": float(amount)},
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
        from db.session import get_engine_for_event_loop, get_session
        engine = get_engine_for_event_loop()
        if engine is None:
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
            "Auto-renew only if you opt in and link your card.\n"
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
            "Auto-renew only if you opt in and link your card.\n"
            "Limited VIP seats available. Click below to secure yours!"
        )
    else:
        benefits = f"{tier_upper} Tier - ₦{amount:,.0f} for {duration_days} days"
    
    return benefits
