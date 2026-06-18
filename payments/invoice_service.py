"""
Invoice Service - Generate Invoices and Receipts for Payments

This module provides:
- Invoice generation for purchases
- Email receipt generation
- PDF invoice support (via template)
- Invoice tracking and status

Usage:
    from payments.invoice_service import generate_invoice
    
    # Generate invoice for payment
    invoice = await generate_invoice(user_id, amount, plan)
"""

import logging
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger("InvoiceService")

# Invoice status
class InvoiceStatus(Enum):
    DRAFT = "draft"
    PENDING = "pending"
    PAID = "paid"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


# Plan pricing (in Naira)
PLAN_PRICING = {
    "premium": {
        "monthly": 5000,
        "quarterly": 13500,
        "yearly": 48000,
    },
    "vip": {
        "monthly": 10000,
        "quarterly": 27000,
        "yearly": 90000,
    },
}


class InvoiceService:
    """
    Invoice and receipt generation service.
    
    Generates invoices for subscription purchases and tracks payment status.
    """
    
    def __init__(self):
        self._company_name = "SignalRankAI"
        self._company_email = "billing@signalrank.ai"
    
    async def generate_invoice(
        self,
        user_id: int,
        amount: float,
        plan: str,
        duration_months: int = 1,
        currency: str = "NGN"
    ) -> Dict[str, Any]:
        """
        Generate a new invoice.
        
        Args:
            user_id: User ID
            amount: Amount in currency units
            plan: Subscription tier
            duration_months: Duration in months
            currency: Currency code
            
        Returns:
            Dict with invoice details
        """
        try:
            invoice_id = f"INV-{uuid.uuid4().hex[:8].upper()}"
            
            # Get user details
            user = await self._get_user(user_id)
            if not user:
                return {"error": "User not found"}
            
            now = datetime.utcnow()
            due_date = now + timedelta(days=7)
            
            invoice = {
                "invoice_id": invoice_id,
                "user_id": user_id,
                "user_email": user.get("email", ""),
                "user_telegram_id": user.get("telegram_user_id"),
                "plan": plan,
                "duration_months": duration_months,
                "amount": amount,
                "currency": currency,
                "status": InvoiceStatus.PENDING.value,
                "created_at": now.isoformat(),
                "due_date": due_date.isoformat(),
                "paid_at": None,
                "items": [
                    {
                        "description": f"{plan.title()} Subscription - {duration_months} month(s)",
                        "quantity": 1,
                        "unit_price": amount,
                        "total": amount,
                    }
                ],
                "subtotal": amount,
                "tax": 0,
                "total": amount,
                "notes": f"Generated via SignalRankAI Payment System",
            }
            
            # Save to DB
            await self._save_invoice(invoice)
            
            logger.info(f"[InvoiceService] Generated invoice {invoice_id} for user {user_id}: {amount}{currency}")
            
            return invoice
            
        except Exception as e:
            logger.error(f"[InvoiceService] Generate error: {e}")
            return {"error": str(e)}
    
    async def get_invoice(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """Get invoice by ID."""
        try:
            from db.session import get_session
            from db.models import RuntimeState
            from sqlalchemy import select
            
            async with get_session() as session:
                result = await session.execute(
                    select(RuntimeState).where(
                        RuntimeState.key == f"invoice:{invoice_id}"
                    )
                )
                state = result.first()
                if state:
                    return state.value
                return None
                
        except Exception as e:
            logger.debug(f"[InvoiceService] Get invoice error: {e}")
            return None
    
    async def mark_paid(
        self,
        invoice_id: str,
        paystack_reference: str
    ) -> bool:
        """Mark invoice as paid."""
        try:
            invoice = await self.get_invoice(invoice_id)
            if not invoice:
                return False
            
            invoice["status"] = InvoiceStatus.PAID.value
            invoice["paid_at"] = datetime.utcnow().isoformat()
            invoice["paystack_reference"] = paystack_reference
            
            await self._save_invoice(invoice)
            
            logger.info(f"[InvoiceService] Invoice {invoice_id} marked as paid")
            return True
            
        except Exception as e:
            logger.error(f"[InvoiceService] Mark paid error: {e}")
            return False
    
    async def cancel_invoice(self, invoice_id: str) -> bool:
        """Cancel an invoice."""
        try:
            invoice = await self.get_invoice(invoice_id)
            if not invoice:
                return False
            
            invoice["status"] = InvoiceStatus.CANCELLED.value
            invoice["cancelled_at"] = datetime.utcnow().isoformat()
            
            await self._save_invoice(invoice)
            
            logger.info(f"[InvoiceService] Invoice {invoice_id} cancelled")
            return True
            
        except Exception as e:
            logger.error(f"[InvoiceService] Cancel error: {e}")
            return False
    
    async def get_user_invoices(
        self,
        user_id: int,
        status: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get invoices for a user."""
        try:
            from db.session import get_session
            from db.models import RuntimeState
            from sqlalchemy import select
            
            async with get_session() as session:
                query = select(RuntimeState).where(
                    RuntimeState.key.like(f"invoice:%")
                )
                
                results = await session.execute(query)
                invoices = []
                
                for row in results.scalars().all():
                    inv = row.value
                    if inv and inv.get("user_id") == user_id:
                        if status is None or inv.get("status") == status:
                            invoices.append(inv)
                
                # Sort by created_at descending
                invoices.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                return invoices[:limit]
                
        except Exception as e:
            logger.debug(f"[InvoiceService] Get user invoices error: {e}")
            return []
    
    async def generate_receipt(
        self,
        invoice: Dict[str, Any]
    ) -> str:
        """
        Generate text receipt for an invoice.
        
        Returns:
            Formatted receipt text
        """
        items_text = ""
        for item in invoice.get("items", []):
            items_text += f"  {item['description']}\n    ${item['total']:,.2f}\n"
        
        receipt = f"""
╔════════════════════════════════════════╗
║         SIGNALRANDAI RECEIPT          ║
╠════════════════════════════════════════╣
║ Invoice: {invoice.get('invoice_id'):<24} ║
║ Date: {invoice.get('created_at', '')[:10]:<24} ║
╠════════════════════════════════════════╣
║ PLAN: {invoice.get('plan', '').title():<24} ║
║ Duration: {invoice.get('duration_months')} month(s){'':<14} ║
╠════════════════════════════════════════╣
{items_text}
║ ──────────────────────
║ TOTAL: {invoice.get('currency')} {invoice.get('total'):,.2f}{'':<17} ║
╠════════════════════════════════════════╣
║ Status: {invoice.get('status', '').upper():<24} ║
║ Paid: {invoice.get('paid_at', 'N/A'):<24} ║
╚════════════════════════════════════════╝
"""
        return receipt
    
    async def send_email_receipt(
        self,
        invoice: Dict[str, Any]
    ) -> bool:
        """
        Send receipt via email (placeholder).
        
        In production, this would integrate with email service.
        """
        # Generate receipt text
        receipt = await self.generate_receipt(invoice)
        
        # Log for now (would send email in production)
        logger.info(f"[InvoiceService] Would send receipt for {invoice.get('invoice_id')}")
        logger.debug(f"[InvoiceService] Receipt:\n{receipt}")
        
        return True
    
    async def _get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user details."""
        try:
            from db.session import get_session
            from db.models import User
            from sqlalchemy import select
            
            async with get_session() as session:
                result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.first()
                
                if user:
                    return {
                        "id": user.id,
                        "telegram_user_id": user.telegram_user_id,
                        "email": user.username,
                        "tier": user.tier,
                    }
                return None
                
        except Exception as e:
            logger.debug(f"[InvoiceService] Get user error: {e}")
            return None
    
    async def _save_invoice(self, invoice: Dict[str, Any]) -> bool:
        """Save invoice to DB."""
        try:
            from db.session import get_session
            from db.models import RuntimeState
            
            async with get_session() as session:
                state = RuntimeState(
                    key=f"invoice:{invoice.get('invoice_id')}",
                    value=invoice,
                )
                session.add(state)
                await session.commit()
                return True
                
        except Exception as e:
            logger.error(f"[InvoiceService] Save invoice error: {e}")
            return False


# Convenience functions
async def generate_invoice(
    user_id: int,
    amount: float,
    plan: str,
    duration_months: int = 1,
    currency: str = "NGN"
) -> Dict[str, Any]:
    """Generate a new invoice."""
    service = InvoiceService()
    return await service.generate_invoice(user_id, amount, plan, duration_months, currency)


async def get_invoice(invoice_id: str) -> Optional[Dict[str, Any]]:
    """Get invoice by ID."""
    service = InvoiceService()
    return await service.get_invoice(invoice_id)


async def get_user_invoices(
    user_id: int,
    status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get user's invoices."""
    service = InvoiceService()
    return await service.get_user_invoices(user_id, status)


if __name__ == "__main__":
    # Quick test
    import asyncio
    
    async def test():
        print("Testing Invoice Service...")
        
        # Generate test invoice
        invoice = await generate_invoice(
            user_id=1,
            amount=5000,
            plan="premium",
            duration_months=1
        )
        print(f"Invoice: {invoice}")
    
    asyncio.run(test())
