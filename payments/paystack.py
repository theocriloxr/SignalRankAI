import hmac
import hashlib
import os
import json
import httpx

PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_BASE_URL = os.getenv("PAYSTACK_BASE_URL", "https://api.paystack.co")

def verify_signature(payload, signature):
    computed = hmac.new(
        PAYSTACK_SECRET.encode(),
        payload,
        hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(computed, signature)

def handle_webhook(request):
    signature = request.headers.get("x-paystack-signature")
    payload = request.body
    if not verify_signature(payload, signature):
        raise Exception("Invalid Paystack signature")
    event = json.loads(payload)
    process_event(event)

async def process_event(event):
    """Process a Paystack webhook event and activate subscription."""
    event_type = event.get("event", "")
    if event_type != "charge.success":
        return {"processed": False, "reason": f"Unhandled event type: {event_type}"}
    
    data = event.get("data", {})
    metadata = data.get("metadata", {})
    
    telegram_user_id = metadata.get("telegram_user_id")
    if not telegram_user_id:
        return {"processed": False, "reason": "No telegram_user_id in metadata"}
    
    tier = metadata.get("tier", "").upper()
    duration_days = metadata.get("duration_days")
    duration = metadata.get("duration", "")
    
    # Map duration string to days if duration_days not provided
    if duration_days is None:
        from paystack.paystack import DURATIONS
        key = f"{tier}_{duration}".upper()
        duration_days = DURATIONS.get(key, 7)
    
    amount = int(data.get("amount", 0)) // 100  # kobo to naira
    
    # Handle extra signals purchase
    if duration == "EXTRA" or metadata.get("extra_count"):
        extra_count = int(metadata.get("extra_count", 1))
        try:
            from core.redis_state import state
            state.add_extra_signals_sync(int(telegram_user_id), int(extra_count), ttl_seconds=86400)
        except Exception:
            pass
        return {"processed": True, "type": "extra_signals", "count": extra_count}
    
    # Activate subscription
    try:
        from db.session import get_session
        from signalrank_telegram.payment_handler import activate_subscription
        async with get_session() as session:
            await activate_subscription(
                session,
                telegram_user_id=int(telegram_user_id),
                tier=tier,
                duration_days=int(duration_days),
                amount_paid=amount,
                payment_provider="paystack",
            )
            await session.commit()
    except Exception as e:
        return {"processed": False, "reason": str(e)}
    
    # Send Telegram confirmation (MarkdownV2 escaped)
    try:
        from signalrank_telegram.bot import application
        bot = application.bot
        from datetime import datetime, timedelta
        import re
        expiry = datetime.utcnow() + timedelta(days=int(duration_days))
        def escape_md(text):
            # Escape all MarkdownV2 special chars
            return re.sub(r'([_\*\[\]()~`>#+\-=|{}.!])', r'\\\1', str(text))
        msg = (
            f"✅ Payment confirmed\\! You're now {escape_md(tier)} tier\\.\n\n"
            f"📅 Active until: {escape_md(expiry.strftime('%Y-%m-%d'))}\n"
            "Use /signals for the latest trading ideas\\."
        )
        await bot.send_message(chat_id=int(telegram_user_id), text=msg, parse_mode="MarkdownV2")
    except Exception:
        pass
    
    # Mark referral as successful (triggers reward check)
    try:
        from engine.referral_manager import ReferralManager
        rm = ReferralManager()
        await rm.mark_referral_successful(int(telegram_user_id))
    except Exception:
        pass
    
    return {"processed": True, "tier": tier, "days": duration_days}

async def verify_payment(reference: str, amount_paid: float) -> bool:
    """Verify a Paystack payment by reference and activate subscription.
    
    Args:
        reference: Paystack transaction reference
        amount_paid: Amount paid in NGN (for validation)
    
    Returns:
        True if payment is verified and valid, False otherwise
    """
    secret = os.getenv("PAYSTACK_SECRET_KEY")
    if not secret:
        return False
    
    try:
        headers = {
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}",
                headers=headers
            )
            
            if response.status_code != 200:
                return False
            
            data = response.json()
            if not data.get("status"):
                return False
            
            tx_data = data.get("data", {})
            tx_status = tx_data.get("status")
            tx_amount = tx_data.get("amount", 0) / 100  # kobo to NGN
            
            # Verify transaction was successful
            if tx_status != "success":
                return False
            
            # Verify amount matches (allow small variance for fees)
            if abs(tx_amount - amount_paid) > 1.0:  # Allow 1 NGN variance
                return False
            
            return True
            
    except Exception as e:
        return False

