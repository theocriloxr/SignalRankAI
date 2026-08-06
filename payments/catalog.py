"""Server-authoritative subscription product catalogue access.

Client applications submit only a product identifier. Prices, tier and duration
are resolved from PostgreSQL so Telegram, web, mobile and API checkouts cannot
supply or alter monetary values.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text


class ProductCatalogueError(ValueError):
    """Raised when a product is unknown, inactive or not publicly purchasable."""


@dataclass(frozen=True, slots=True)
class CheckoutProduct:
    product_id: str
    tier: str
    display_name: str
    duration_days: int
    currency: str
    price_kobo: int

    @property
    def price_ngn(self) -> int:
        return int(self.price_kobo // 100)


async def resolve_checkout_product(
    session: Any,
    product_id: str,
    *,
    currency: str = "NGN",
) -> CheckoutProduct:
    product_key = str(product_id or "").strip().lower()
    currency_code = str(currency or "NGN").strip().upper()
    if not product_key:
        raise ProductCatalogueError("product_id_required")

    product = (
        await session.execute(
            text(
                "SELECT product_id,tier,display_name,duration_days,active "
                "FROM subscription_products WHERE product_id=:product_id"
            ),
            {"product_id": product_key},
        )
    ).mappings().first()
    if not product or not bool(product.get("active")):
        raise ProductCatalogueError("product_unavailable")

    price = (
        await session.execute(
            text(
                "SELECT currency,price_kobo FROM subscription_prices "
                "WHERE product_id=:product_id AND currency=:currency "
                "AND effective_from<=CURRENT_TIMESTAMP "
                "AND (effective_until IS NULL OR effective_until>CURRENT_TIMESTAMP) "
                "ORDER BY effective_from DESC,id DESC LIMIT 1"
            ),
            {"product_id": product_key, "currency": currency_code},
        )
    ).mappings().first()
    if not price:
        raise ProductCatalogueError("active_price_unavailable")

    price_kobo = int(price.get("price_kobo") or 0)
    if price_kobo <= 0:
        # Professional/Institutional contact-sales rows deliberately use zero.
        raise ProductCatalogueError("product_requires_contact_sales")

    duration_days = int(product.get("duration_days") or 0)
    if duration_days <= 0:
        raise ProductCatalogueError("product_duration_invalid")

    return CheckoutProduct(
        product_id=str(product["product_id"]),
        tier=str(product["tier"]).strip().lower(),
        display_name=str(product.get("display_name") or product["product_id"]),
        duration_days=duration_days,
        currency=str(price.get("currency") or currency_code).upper(),
        price_kobo=price_kobo,
    )


__all__ = ["CheckoutProduct", "ProductCatalogueError", "resolve_checkout_product"]
