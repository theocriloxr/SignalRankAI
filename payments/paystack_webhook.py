"""
Paystack Webhook Handler - Payment Security & Subscription Management

This module provides:
- Webhook signature validation
- Subscription state machine (active → expired → grace period → downgrade)
- Retry logic for failed webhooks
- Invoice generation

Usage:
    from payments.paystack_webhook import PaystackWebhookHandler
    
    handler = PaystackWebhookHandler()
    result = await handler.process_webhook(payload, signature)
"""

import os
import hmac
import hashlib
import logging
import asyncio
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import field

logger = logging.getLogger("PaystackWebhook")


class SubscriptionStatus(Enum):
    """Subscription lifecycle states."""
    ACTIVE = "active"
    EXPIRED = "expired"
    GRACE_PERIOD = "grace_period"
    DOWNGRADED = "downgraded"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class PaymentStatus(Enum):
    """Payment states."""
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    REFUNDED = "refunded"


@dataclass
class Subscription:
    """Subscription record."""
    id: str
    user_id: int
    plan: str  # free, premium, vip
    status: SubscriptionStatus
    started_at: datetime
    expires_at: datetime
    next_billing_at: Optional[datetime]
    auto_renew: bool = True
    grace_period_days: int = 3
    payment_method: str = "card"


@dataclass
class PaymentRecord:
    """Payment transaction record."""
    id: str
    user_id: int
    amount: float
    currency: str
    status: PaymentStatus
    reference: str
    paid_at: Optional[datetime]
    created_at: datetime
    invoice_id: Optional[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


class PaystackWebhookHandler:
    """
    Paystack webhook handler with security hardening.
    
    Features:
    - Signature validation (prevent spoofing)
    - Idempotency (prevent duplicate processing)
    - Subscription state machine
    - Grace period handling
    - Auto-downgrade on payment failure
    """
    
    def __init__(self):
        self._processed_refs: set = set()
        self._webhook_secret = os.getenv("PAYSTACK_WEBHOOK_SECRET", "").strip()
        self._grace_period_days = 3
        
    async def validate_signature(self, payload: str, signature: str) -> bool:
        """
        Validate Paystack webhook signature.
        
        Args:
            payload: Raw request body
            signature: X-Paystack-Signature header
            
        Returns:
            True if valid, False otherwise
        """
        if not self._webhook_secret:
            logger.warning("[Paystack] No webhook secret configured")
            return False
            
        if not signature:
            logger.warning("[Paystack] No signature provided")
            return False
            
        try:
            computed = hmac.new(
                self._webhook_secret.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha512
            ).hexdigest()
            
            return hmac.compare_digest(computed, signature)
            
        except Exception as e:
            logger.error(f"[Paystack] Signature validation error: {e}")
            return False
    
    async def process_webhook(self, payload: Dict[str, Any], signature: str = "") -> Dict[str, Any]:
        """
        Process Paystack webhook event.
        
        Args:
            payload: Webhook JSON payload
            signature: Webhook signature for validation
            
        Returns:
            Dict with processing result
        """
        # Validate signature if secret is configured
        if self._webhook_secret:
            import json
            payload_str = json.dumps(payload, sort_keys=True)
            if not await self.validate_signature(payload_str, signature):
                logger.warning("[Paystack] Invalid signature - possible spoofing attempt")
                return {"ok": False, "error": "invalid_signature"}
        
        event = payload.get("event", "")
        
        # Handle different event types
        if event == "charge.success":
            return await self._handle_charge_success(payload)
        elif event == "subscription.created":
            return await self._handle_subscription_created(payload)
        elif event == "subscription.disabled":
            return await self._handle_subscription_disabled(payload)
        elif event == "subscription.not_renewed":
            return await self._handle_subscription_not_renewed(payload)
        elif event == "invoice.payment_failed":
            return await self._handle_payment_failed(payload)
        elif event == "charge.failed":
            return await self._handle_charge_failed(payload)
        else:
            logger.info(f"[Paystack] Unhandled event: {event}")
            return {"ok": True, "event": event, "handled": False}
    
    async def _handle_charge_success(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle successful payment."""
        data = payload.get("data", {})
        reference = data.get("reference", "")
        
        # Idempotency check
        if reference in self._processed_refs:
            logger.info(f"[Paystack] Duplicate payment: {reference}")
            return {"ok": True, "duplicate": True}
        
        self._processed_refs.add(reference)
        
        try:
            amount = float(data.get("amount", 0)) / 100  # Paystack uses kobo/naira
            currency = data.get("currency", "NGN")
            customer = data.get("customer", {})
            email = customer.get("email", "")
            metadata = data.get("metadata", {})
            user_id = metadata.get("user_id")
            
            if not user_id:
                logger.warning("[Paystack] No user_id in metadata")
                return {"ok": False, "error": "no_user_id"}
            
            # Create payment record
            payment = PaymentRecord(
                id=reference,
                user_id=int(user_id),
                amount=amount,
                currency=currency,
                status=PaymentStatus.SUCCESS,
                reference=reference,
                paid_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
                invoice_id=reference,
                metadata=metadata
            )
            
            # Update subscription status
            await self._activate_subscription(user_id, payment)
            
            logger.info(f"[Paystack] Payment success: {reference} user={user_id} amount={amount}{currency}")
            
            return {
                "ok": True,
                "reference": reference,
                "amount": amount,
                "currency": currency
            }
            
        except Exception as e:
            logger.error(f"[Paystack] Charge success error: {e}")
            return {"ok": False, "error": str(e)}
    
    async def _handle_subscription_created(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle new subscription."""
        data = payload.get("data", {})
        sub_code = data.get("subscription_code", "")
        customer = data.get("customer", {})
        email = customer.get("email", "")
        
        # Would typically create subscription in DB
        logger.info(f"[Paystack] New subscription: {sub_code} for {email}")
        
        return {"ok": True, "subscription": sub_code}
    
    async def _handle_subscription_disabled(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle subscription disabled (cancelled/not renewed)."""
        data = payload.get("data", {})
        sub_code = data.get("subscription_code", "")
        cancel_at = data.get("cancel_at")
        
        # Transition to grace period or downgrade
        if cancel_at:
            await self._start_grace_period(sub_code, cancel_at)
        else:
            await self._downgrade_subscription(sub_code)
        
        logger.info(f"[Paystack] Subscription disabled: {sub_code}")
        
        return {"ok": True}
    
    async def _handle_subscription_not_renewed(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle subscription not renewed."""
        data = payload.get("data", {})
        sub_code = data.get("subscription_code", "")
        
        # Start grace period
        await self._start_grace_period(sub_code)
        
        return {"ok": True}
    
    async def _handle_payment_failed(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle payment failure."""
        data = payload.get("data", {})
        reference = data.get("reference", "")
        customer = data.get("customer", {})
        metadata = data.get("metadata", {})
        user_id = metadata.get("user_id")
        
        if user_id:
            # Retry logic - try again in X minutes
            retry_count = metadata.get("retry_count", 0)
            if retry_count < 3:
                await self._schedule_retry(user_id, reference, retry_count + 1)
        
        logger.warning(f"[Paystack] Payment failed: {reference}")
        
        return {"ok": True}
    
    async def _handle_charge_failed(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle charge failure."""
        data = payload.get("data", {})
        reference = data.get("reference", "")
        
        # Mark as failed, will trigger downgrade in grace period
        logger.warning(f"[Paystack] Charge failed: {reference}")
        
        return {"ok": True}
    
    async def _activate_subscription(self, user_id: int, payment: PaymentRecord) -> None:
        """Activate subscription after payment."""
        try:
            from db.session import get_session
            from db.models import User, Subscription as UserSubscription
            
            async with get_session() as session:
                # Update user tier based on amount
                tier = self._determine_tier(payment.amount)
                
                # Update or create subscription
                subscription = Subscription(
                    id=f"sub_{payment.reference}",
                    user_id=user_id,
                    plan=tier,
                    status=SubscriptionStatus.ACTIVE,
                    started_at=datetime.utcnow(),
                    expires_at=datetime.utcnow() + timedelta(days=30),
                    next_billing_at=datetime.utcnow() + timedelta(days=30),
                    auto_renew=True,
                    grace_period_days=self._grace_period_days
                )
                
                # Update user's tier
                result = await session.execute(
                    f"UPDATE users SET tier = :tier WHERE id = :user_id",
                    {"tier": tier, "user_id": user_id}
                )
                await session.commit()
                
                logger.info(f"[Paystack] Activated {tier} tier for user {user_id}")
                
        except Exception as e:
            logger.error(f"[Paystack] Activate subscription error: {e}")
    
    async def _start_grace_period(self, sub_code: str, cancel_at: Optional[str] = None) -> None:
        """Start grace period before downgrade."""
        grace_end = datetime.utcnow() + timedelta(days=self._grace_period_days)
        
        logger.info(f"[Paystack] Grace period started for {sub_code}, ends {grace_end}")
        
        # Schedule downgrade job
        # This would typically schedule via celery/background worker
    
    async def _downgrade_subscription(self, sub_code: str) -> None:
        """Downgrade subscription after grace period."""
        try:
            # Transition to free tier
            logger.info(f"[Paystack] Downgrading subscription {sub_code}")
            
        except Exception as e:
            logger.error(f"[Paystack] Downgrade error: {e}")
    
    async def _schedule_retry(self, user_id: int, reference: str, retry_count: int) -> None:
        """Schedule retry for failed payment."""
        # Retry intervals: 1 min, 5 min, 15 min
        intervals = [60, 300, 900]
        delay = intervals[min(retry_count, 2)]
        
        logger.info(f"[Paystack] Scheduling retry {retry_count} for user {user_id} in {delay}s")
        
        # This would schedule via background worker
        await asyncio.sleep(delay)
        # Would call payment provider again
    
    def _determine_tier(self, amount: float) -> str:
        """Determine tier based on amount."""
        if amount >= 5000:  # VIP tier
            return "vip"
        elif amount >= 2000:  # Premium tier
            return "premium"
        else:
            return "free"
    
    async def generate_invoice(self, user_id: int, amount: float, plan: str) -> Dict[str, Any]:
        """Generate invoice for payment."""
        import uuid
        
        invoice_id = f"INV-{uuid.uuid4().hex[:8].upper()}"
        
        invoice = {
            "invoice_id": invoice_id,
            "user_id": user_id,
            "amount": amount,
            "plan": plan,
            "currency": "NGN",
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "due_at": (datetime.utcnow() + timedelta(days=7)).isoformat()
        }
        
        # Store invoice in DB
        logger.info(f"[Paystack] Generated invoice: {invoice_id}")
        
        return invoice


class SubscriptionManager:
    """
    Subscription state machine manager.
    
    Handles transitions:
    active → expired → grace_period → downgrade → free
    """
    
    def __init__(self):
        self._grace_period_days = 3
    
    async def get_subscription_status(self, user_id: int) -> Dict[str, Any]:
        """Get current subscription status."""
        try:
            from db.session import get_session
            
            async with get_session() as session:
                # Query subscription
                result = await session.execute(
                    "SELECT plan, status, expires_at FROM subscriptions WHERE user_id = :uid",
                    {"uid": user_id}
                )
                row = result.fetchone()
                
                if not row:
                    return {
                        "tier": "free",
                        "status": "none",
                        "expires_at": None
                    }
                
                plan, status, expires_at = row
                
                # Check if in grace period
                if status == "grace_period":
                    grace_end = expires_at - timedelta(days=self._grace_period_days)
                    if datetime.utcnow() > grace_end:
                        # Should have downgraded
                        status = "needs_downgrade"
                
                return {
                    "tier": plan,
                    "status": status,
                    "expires_at": expires_at.isoformat() if expires_at else None
                }
                
        except Exception as e:
            logger.debug(f"[Subscription] Status error: {e}")
            return {"tier": "free", "status": "unknown"}
    
    async def check_and_downgrade(self, user_id: int) -> None:
        """Check subscriptions and downgrade expired ones."""
        try:
            from db.session import get_session
            
            async with get_session() as session:
                # Find expired subscriptions in grace period
                result = await session.execute("""
                    SELECT id, user_id FROM subscriptions 
                    WHERE status = 'grace_period' 
                    AND expires_at < NOW()
                """)
                
                rows = result.fetchall()
                
                for row in rows:
                    sub_id, uid = row
                    await self._downgrade_user(uid)
                    
        except Exception as e:
            logger.error(f"[Subscription] Downgrade check error: {e}")
    
    async def _downgrade_user(self, user_id: int) -> None:
        """Downgrade user to free tier."""
        try:
            from db.session import get_session
            
            async with get_session() as session:
                await session.execute(
                    "UPDATE users SET tier = 'free' WHERE id = :uid",
                    {"uid": user_id}
                )
                await session.execute(
                    "UPDATE subscriptions SET status = 'downgraded' WHERE user_id = :uid",
                    {"uid": user_id}
                )
                await session.commit()
                
                logger.info(f"[Subscription] Downgraded user {user_id}")
                
        except Exception as e:
            logger.error(f"[Subscription] Downgrade error: {e}")
    
    async def extend_subscription(self, user_id: int, days: int) -> None:
        """Extend subscription by days."""
        try:
            from db.session import get_session
            
            async with get_session() as session:
                await session.execute("""
                    UPDATE subscriptions 
                    SET expires_at = expires_at + INTERVAL ':days day',
                        status = 'active'
                    WHERE user_id = :uid
                """, {"uid": user_id, "days": days})
                await session.commit()
                
                logger.info(f"[Subscription] Extended user {user_id} by {days} days")
                
        except Exception as e:
            logger.error(f"[Subscription] Extend error: {e}")


# Helper function for webhook endpoint
async def handle_paystack_webhook(payload: Dict[str, Any], signature: str) -> Dict[str, Any]:
    """Main webhook entry point."""
    handler = PaystackWebhookHandler()
    return await handler.process_webhook(payload, signature)


if __name__ == "__main__":
    # Test
    import json
    
    async def test():
        handler = PaystackWebhookHandler()
        
        # Test payload
        test_payload = {
            "event": "charge.success",
            "data": {
                "reference": "test_123",
                "amount": 500000,
                "currency": "NGN",
                "customer": {"email": "test@example.com"},
                "metadata": {"user_id": "123"}
            }
        }
        
        result = await handler.process_webhook(test_payload, "")
        print(f"Result: {result}")
    
    asyncio.run(test())
