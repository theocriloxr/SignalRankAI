from utils.timeutils import now_utc_naive
import hmac
import hashlib
import os
import json
import logging
import httpx

logger = logging.getLogger(__name__)

PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_BASE_URL = os.getenv("PAYSTACK_BASE_URL", "https://api.paystack.co")
# Optional provider source allow-list.  An empty list keeps local/staging
# compatibility; production can set PAYSTACK_WEBHOOK_IP_WHITELIST to a
# comma-separated list and the dedicated ingress router will enforce it.
PAYSTACK_WEBHOOK_IP_WHITELIST = frozenset(
    item.strip()
    for item in str(os.getenv("PAYSTACK_WEBHOOK_IP_WHITELIST") or "").split(",")
    if item.strip()
)

_DEFAULT_DURATIONS = {
    "PREMIUM_WEEKLY": 7,
    "PREMIUM_MONTHLY": 30,
    "PREMIUM_QUARTERLY": 90,
    "PREMIUM_YEARLY": 365,
    "VIP_WEEKLY": 7,
    "VIP_MONTHLY": 30,
    "WEEKLY_PLAN": 7,
}

_PLAN_AMOUNTS_NGN = {
    "PREMIUM_WEEKLY": int(os.getenv("PREMIUM_WEEKLY_PRICE_NGN", "8000") or 8000),
    "PREMIUM_MONTHLY": int(os.getenv("PREMIUM_MONTHLY_PRICE_NGN", "24000") or 24000),
    "PREMIUM_QUARTERLY": int(os.getenv("PREMIUM_QUARTERLY_PRICE_NGN", "56000") or 56000),
    "PREMIUM_YEARLY": int(os.getenv("PREMIUM_YEARLY_PRICE_NGN", "192000") or 192000),
    "VIP_WEEKLY": int(os.getenv("VIP_WEEKLY_PRICE_NGN", "16000") or 16000),
    "VIP_MONTHLY": int(os.getenv("VIP_MONTHLY_PRICE_NGN", os.getenv("VIP_PRICE_NGN", "40000")) or 40000),
    "WEEKLY_PLAN": int(os.getenv("WEEKLY_PLAN_PRICE_NGN", "5000") or 5000),
}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def verify_signature(payload, signature):
    from payments.paystack_policy import verify_paystack_event_signature
    return verify_paystack_event_signature(payload, signature)


def verify_webhook_signature(payload: bytes | str, signature: str | None) -> bool:
    """Compatibility alias used by the dedicated FastAPI webhook router."""
    return verify_signature(payload, signature)

def handle_webhook(request):
    signature = request.headers.get("x-paystack-signature")
    payload = request.body
    if not verify_signature(payload, signature):
        raise Exception("Invalid Paystack signature")
    event = json.loads(payload)
    process_event(event)

async def process_event(event):
    """Process a Paystack webhook event and activate subscription."""
    if not isinstance(event, dict):
        return {"processed": False, "reason": "Invalid payment event"}
    event_type = event.get("event", "")
    data = event.get("data", {})
    if event_type in {"transfer.success", "transfer.failed", "transfer.reversed"}:
        if not isinstance(data, dict):
            return {"processed": False, "reason": "Invalid transfer data"}
        from payments.payout_service import apply_transfer_event
        applied = await apply_transfer_event(str(event_type), data)
        return {"processed": bool(applied), "type": "payout_transfer", "event": event_type}
    if event_type == "subscription.disable":
        applied = await process_subscription_disable(dict(data or {}))
        return {"processed": bool(applied), "type": "subscription_disable"}
    if event_type in {
        "subscription.create",
        "subscription.not_renew",
        "invoice.payment_failed",
        "customeridentification.success",
    }:
        # These lifecycle notices do not grant entitlements. They are terminal
        # acknowledgements so the durable inbox does not retry them forever.
        return {"processed": False, "ignored": True, "reason": f"No entitlement mutation for {event_type}"}
    if event_type != "charge.success":
        return {"processed": False, "ignored": True, "reason": f"Unhandled event type: {event_type}"}
    
    if not isinstance(data, dict):
        return {"processed": False, "reason": "Invalid payment data"}
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        return {"processed": False, "reason": "Invalid payment metadata"}

    # A charge event without a durable provider reference or a positive NGN
    # amount cannot be safely applied to entitlements.  Signature validity
    # alone proves origin, not product/user/amount correctness.
    reference = str(data.get("reference") or "").strip()
    if not reference:
        return {"processed": False, "reason": "Missing payment reference"}
    currency = str(data.get("currency") or "NGN").strip().upper()
    if currency != "NGN":
        return {"processed": False, "reason": "Unsupported payment currency"}
    
    telegram_user_id = metadata.get("telegram_user_id")
    if not telegram_user_id:
        return {"processed": False, "reason": "No telegram_user_id in metadata"}
    
    tier = metadata.get("tier", "").upper()
    duration_days = metadata.get("duration_days")
    duration = metadata.get("duration", "")
    
    # Map duration string to days if duration_days not provided
    if duration_days is None:
        try:
            from paystack.paystack import DURATIONS  # type: ignore
        except Exception:
            DURATIONS = _DEFAULT_DURATIONS
        key = f"{tier}_{duration}".upper()
        duration_days = DURATIONS.get(key, 7)
    
    try:
        amount = int(data.get("amount", 0)) // 100  # kobo to naira
    except (TypeError, ValueError):
        return {"processed": False, "reason": "Invalid payment amount"}
    if amount <= 0:
        return {"processed": False, "reason": "Invalid payment amount"}

    if _env_bool("PAYSTACK_VERIFY_TRANSACTION_ON_WEBHOOK", False):
        if not await verify_payment(reference, float(amount)):
            return {"processed": False, "reason": "Provider transaction verification failed"}

    from payments.paystack_policy import evaluate_paystack_operation
    paystack_policy = evaluate_paystack_operation(
        telegram_user_id=int(telegram_user_id),
        amount_ngn=float(amount),
    )
    if not paystack_policy.allowed:
        return {
            "processed": False,
            "reason": f"Paystack runtime policy blocked event: {paystack_policy.reason}",
        }

    # Validate catalog-backed metadata when a product duration is supplied.
    # Unknown/legacy plans remain processable only when they carry an explicit
    # amount; known plans never silently accept a mismatched charge.
    duration_key = str(duration or "").strip().upper()
    if duration_key and duration_key != "EXTRA":
        plan_key = f"{tier}_{duration_key}"
        expected_amount = _PLAN_AMOUNTS_NGN.get(plan_key)
        if expected_amount is not None and amount != expected_amount:
            return {
                "processed": False,
                "reason": "Payment amount does not match product catalog",
            }
    expected_meta_amount = metadata.get("amount_ngn")
    if expected_meta_amount is not None:
        try:
            if abs(float(expected_meta_amount) - float(amount)) > 0.01:
                return {"processed": False, "reason": "Payment amount mismatch"}
        except (TypeError, ValueError):
            return {"processed": False, "reason": "Invalid product amount"}
    
    # Handle extra signals purchase
    if duration == "EXTRA" or metadata.get("extra_count"):
        try:
            extra_count = int(metadata.get("extra_count", 1))
        except (TypeError, ValueError):
            return {"processed": False, "reason": "Invalid extra signal count"}
        if extra_count < 1 or extra_count > 100:
            return {"processed": False, "reason": "Invalid extra signal count"}
        if amount != 600 * extra_count:
            return {
                "processed": False,
                "reason": "Payment amount does not match extra-signal catalog",
            }
        try:
            from db.models import PaymentEvent
            from db.pg_features import record_payment_event
            from db.session import get_session
            from sqlalchemy import select
            async with get_session(label="payment.extra_signals", timeout_seconds=10.0) as session:
                existing_event = (await session.execute(
                    select(PaymentEvent).where(PaymentEvent.paystack_reference == reference)
                )).scalar_one_or_none()
                if existing_event is None:
                    existing_event = await record_payment_event(
                        session,
                        telegram_user_id=int(telegram_user_id),
                        paystack_reference=reference,
                        amount_ngn=amount,
                        currency=currency,
                        kind="extra_signals",
                        duration_days=1,
                        meta={"extra_count": extra_count, "verified_provider": True, "credit_applied": False},
                    )
                    await session.commit()
            from core.redis_state import state
            credited = state.add_extra_signals_once_sync(
                int(telegram_user_id), int(extra_count), reference, ttl_seconds=86400
            )
            if credited is None:
                return {"processed": False, "reason": "Extra-signal credit storage unavailable"}
            async with get_session(label="payment.extra_signals.complete", timeout_seconds=10.0) as session:
                row = (await session.execute(
                    select(PaymentEvent).where(PaymentEvent.paystack_reference == reference).with_for_update()
                )).scalar_one()
                row.meta = {**dict(row.meta or {}), "credit_applied": True, "credited_total": int(credited)}
                await session.commit()
        except Exception as exc:
            return {"processed": False, "reason": f"Extra-signal credit failed: {type(exc).__name__}"}
        return {"processed": True, "type": "extra_signals", "count": extra_count}
    
    # Activate subscription
    try:
        from db.models import PaymentEvent
        from db.pg_features import record_payment_event
        from db.session import get_session
        from sqlalchemy import select
        # Use the repository primitive as the single entitlement authority.
        # The Telegram helper historically exposed an incompatible signature
        # and is not present in minimal web deployments.
        from db.repository import activate_subscription
        async with get_session(label="payment.subscription", timeout_seconds=10.0) as session:
            existing_event = (await session.execute(
                select(PaymentEvent).where(PaymentEvent.paystack_reference == reference)
            )).scalar_one_or_none()
            if existing_event is not None:
                return {
                    "processed": True,
                    "idempotent": True,
                    "tier": existing_event.tier or str(tier).lower(),
                    "days": existing_event.duration_days or int(duration_days),
                }
            await record_payment_event(
                session,
                telegram_user_id=int(telegram_user_id),
                paystack_reference=reference,
                amount_ngn=amount,
                currency=currency,
                kind="subscription",
                tier=str(tier).lower(),
                duration_days=int(duration_days),
                plan_code=str(data.get("plan", {}).get("plan_code") or metadata.get("plan_code") or "") or None,
                meta={"event": event_type, "verified_provider": True},
            )
            await activate_subscription(
                session,
                telegram_user_id=int(telegram_user_id),
                tier=tier,
                duration_days=int(duration_days),
                paystack_reference=reference,
                meta={
                    "provider": "paystack",
                    "amount_ngn": amount,
                    "currency": str(data.get("currency") or "NGN"),
                    "event": event_type,
                },
            )
            # Record conversion in the same transaction. Referral rewards are
            # granted by qualified signups; payment conversion is analytics-only
            # and must never run a competing reward manager.
            from db.pg_features import record_referral_conversion
            conversion = await record_referral_conversion(
                session,
                referred_telegram_user_id=int(telegram_user_id),
                payment_reference=reference,
            )
            logger.info(
                "[paystack_referral_conversion] telegram_user_id=%s reference=%s result=%s",
                telegram_user_id,
                reference,
                conversion,
            )
            await session.commit()
    except Exception as e:
        # The payment_events unique reference is the authoritative concurrency
        # guard. A concurrent duplicate cannot partially extend entitlement.
        if type(e).__name__ == "IntegrityError":
            return {"processed": True, "idempotent": True, "tier": str(tier).lower(), "days": int(duration_days)}
        return {"processed": False, "reason": str(e)}
    
    # Send Telegram confirmation (MarkdownV2 escaped)
    try:
        from signalrank_telegram.bot import application
        bot = application.bot
        from datetime import datetime, timedelta
        import re
        expiry = now_utc_naive() + timedelta(days=int(duration_days))
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


async def process_charge_success(data: dict) -> bool:
    result = await process_event({"event": "charge.success", "data": dict(data or {})})
    return bool((result or {}).get("processed"))


async def process_subscription_create(data: dict) -> bool:
    """Handle provider subscription notifications without granting access.

    Entitlements are granted only on a successful, amount-bearing charge.
    Subscription lifecycle notices are acknowledged for idempotent delivery;
    they cannot activate a plan on their own.
    """
    return True


async def process_subscription_disable(data: dict) -> bool:
    """Best-effort downgrade on provider cancellation."""
    try:
        metadata = dict((data or {}).get("metadata") or {})
        telegram_user_id = metadata.get("telegram_user_id")
        if not telegram_user_id:
            return False
        from payments.paystack_policy import evaluate_paystack_operation
        policy = evaluate_paystack_operation(telegram_user_id=int(telegram_user_id))
        if not policy.allowed:
            return False
        from db.session import get_session
        from db.models import User
        from sqlalchemy import select

        async with get_session() as session:
            row = await session.execute(
                select(User).where(User.telegram_user_id == int(telegram_user_id))
            )
            user = row.scalars().first()
            if user is None:
                return False
            user.tier = "free"
            user.auto_renew = False
            await session.commit()
        return True
    except Exception:
        return False


async def _lookup_user_by_email(email: str) -> int | None:
    """Resolve a Telegram id for legacy payment notifications."""
    try:
        from db.session import get_session
        from db.models import User
        from sqlalchemy import select

        async with get_session() as session:
            row = await session.execute(select(User).where(User.username == str(email)))
            user = row.scalars().first()
            return int(user.telegram_user_id) if user is not None else None
    except Exception:
        return None

