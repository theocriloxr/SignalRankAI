"""Central authorization contract for original signals, retries, and lifecycle sends."""

from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.env import runtime_environment_name
from core.tier_policy import get_entitlements, normalize_tier
from db.access import resolve_product_tier
from db.models import SignalDelivery, User
from utils.timeutils import now_utc_naive


@dataclass(frozen=True, slots=True)
class DeliveryAuthorization:
    allowed: bool
    code: str
    tier: str
    reason: str = ""


def _restricted_audience() -> set[int]:
    app_env = runtime_environment_name("development")
    explicit = str(os.getenv("DELIVERY_AUDIENCE_RESTRICTION_MODE", "0") or "0").lower() in {
        "1", "true", "yes", "on",
    }
    # A configured list is diagnostic-only in normal production. Restriction
    # requires an explicit non-production/testing mode.
    if app_env == "production" and not explicit:
        return set()
    if not explicit and not any(
        str(os.getenv(name, "0") or "0").lower() in {"1", "true", "yes", "on"}
        for name in ("PUBLIC_TESTING_MODE", "FULL_SYSTEM_STAGING_TEST_MODE", "FULL_SYSTEM_STAGING_TEST_ACTIVE")
    ):
        return set()
    values: set[int] = set()
    for part in str(os.getenv("DELIVERY_AUDIENCE_ALLOWLIST", "") or "").replace(";", ",").split(","):
        try:
            values.add(int(part.strip()))
        except (TypeError, ValueError):
            continue
    return values


async def authorize_signal_delivery(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    signal: dict | None = None,
    enforce_daily_limit: bool = True,
) -> DeliveryAuthorization:
    """Authorize a recipient without any manual owner-approval requirement."""
    user = (
        await session.execute(
            select(User).where(User.telegram_user_id == int(telegram_user_id)).limit(1)
        )
    ).scalar_one_or_none()
    if user is None:
        return DeliveryAuthorization(False, "USER_MISSING", "none", "user has not completed onboarding")
    if bool(user.is_blocked) or bool(user.is_suspended):
        return DeliveryAuthorization(False, "ACCOUNT_BLOCKED", "none", "account is blocked or suspended")
    if not bool(user.accepted_terms):
        return DeliveryAuthorization(False, "TERMS_REQUIRED", "none", "terms must be accepted")
    audience = _restricted_audience()
    if audience and int(telegram_user_id) not in audience:
        return DeliveryAuthorization(False, "TEST_AUDIENCE_RESTRICTED", "none", "testing audience restriction")

    # Reuse the caller's session. Opening a second session here can deadlock a
    # two-connection Railway pool while delivery authorization owns one lane.
    tier = str(await resolve_product_tier(session, user) or "free").lower()
    if tier == "none":
        return DeliveryAuthorization(False, "ACCOUNT_BLOCKED", tier, "account is blocked or suspended")
    policy = get_entitlements(tier)
    payload = dict(signal or {})
    score = float(payload.get("score") or 0.0)
    if payload and score < float(policy.minimum_signal_score):
        return DeliveryAuthorization(False, "SCORE_BELOW_TIER_MINIMUM", tier)
    asset_class = str(payload.get("asset_class") or "").strip().lower()
    if asset_class and asset_class not in set(policy.allowed_asset_classes):
        return DeliveryAuthorization(False, "ASSET_CLASS_NOT_ENTITLED", tier)
    profile = str(payload.get("trade_profile") or "").strip().lower()
    if profile and profile not in set(policy.allowed_profiles):
        return DeliveryAuthorization(False, "PROFILE_NOT_ENTITLED", tier)

    if enforce_daily_limit:
        start = now_utc_naive().replace(hour=0, minute=0, second=0, microsecond=0)
        delivered = int((await session.execute(
            select(func.count(SignalDelivery.id)).where(
                SignalDelivery.user_id == int(user.id),
                SignalDelivery.sent_ok.is_(True),
                SignalDelivery.telegram_message_id.is_not(None),
                SignalDelivery.delivered_at >= start,
            )
        )).scalar() or 0)
        if delivered >= int(policy.daily_signal_limit):
            return DeliveryAuthorization(False, "DAILY_LIMIT_REACHED", tier)
    return DeliveryAuthorization(True, "AUTHORIZED", tier)


__all__ = ["DeliveryAuthorization", "authorize_signal_delivery"]
