from __future__ import annotations

import os
import json
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from db.models import Subscription, User, Signal, Outcome, DecisionLog, ProcessedWebhookEvent, ApiToken
from db.session import get_session

ACTIVE_PARTIAL_OUTCOME_STATUSES = ("tp1", "tp2")


def _env_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or str(default)).strip())
    except Exception:
        return default


async def get_active_subscription(
    session: AsyncSession,
    telegram_user_id: int,
    tier: str,
) -> Optional[Subscription]:
    tier_norm = normalize_tier(tier)
    now = datetime.utcnow()
    res = await session.execute(
        select(Subscription)
        .join(User, User.id == Subscription.user_id)
        .where(
            User.telegram_user_id == telegram_user_id,
            Subscription.status == "active",
            Subscription.tier == tier_norm,
            Subscription.expires_at.is_not(None),
            Subscription.expires_at > now,
        )
        .order_by(Subscription.expires_at.desc())
    )
    return res.scalars().first()


async def count_active_vip_users(
    session: AsyncSession,
    exclude_telegram_user_ids: set[int] | None = None,
) -> int:
    now = datetime.utcnow()
    q = (
        select(func.count(func.distinct(Subscription.user_id)))
        .select_from(Subscription)
        .join(User, User.id == Subscription.user_id)
        .where(
            Subscription.status == "active",
            Subscription.tier == "vip",
            Subscription.expires_at.is_not(None),
            Subscription.expires_at > now,
        )
    )

    if exclude_telegram_user_ids:
        q = q.where(User.telegram_user_id.not_in(exclude_telegram_user_ids))

    res = await session.execute(q)
    return int(res.scalar() or 0)


def normalize_tier(tier: str) -> str:
    t = (tier or "").strip().lower()
    if t in {"vip", "owner", "admin"}:
        return "vip"
    if t in {"premium", "pro"}:
        return "premium"
    return "free"


async def get_or_create_user(
    session: AsyncSession,
    telegram_user_id: int,
    username: Optional[str] = None,
    tier: Optional[str] = None,
) -> User:
    res = await session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
    user = res.scalar_one_or_none()
    if user is not None:
        if username and user.username != username:
            user.username = username
        if tier:
            try:
                user.tier = str(tier).strip().lower()[:16]
            except Exception:
                pass
            await session.flush()
        return user

    user = User(telegram_user_id=telegram_user_id, username=username, tier=(str(tier).strip().lower()[:16] if tier else "free"))
    session.add(user)
    try:
        await session.flush()
        return user
    except IntegrityError:
        # Another concurrent request likely created the same telegram_user_id.
        # Roll back the failed INSERT and re-select.
        await session.rollback()
        res2 = await session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
        existing2 = res2.scalar_one_or_none()
        if existing2 is None:
            raise
        if username and existing2.username != username:
            existing2.username = username
            await session.flush()
        return existing2


async def activate_subscription(
    session: AsyncSession,
    telegram_user_id: int,
    tier: str,
    duration_days: int,
    paystack_reference: Optional[str],
    meta: Dict[str, Any],
) -> Subscription:
    # Idempotency: if reference already exists, return existing subscription.
    if paystack_reference:
        res = await session.execute(
            select(Subscription).where(Subscription.paystack_reference == paystack_reference)
        )
        existing = res.scalar_one_or_none()
        if existing is not None:
            return existing

    user = await get_or_create_user(session, telegram_user_id)

    now = datetime.utcnow()
    tier_norm = normalize_tier(tier)
    add_days = max(int(duration_days), 1)

    # Renewal behavior: if user already has an active subscription for the same tier, extend it.
    existing = await get_active_subscription(session, telegram_user_id=telegram_user_id, tier=tier_norm)
    if existing is not None and existing.expires_at is not None:
        existing.expires_at = existing.expires_at + timedelta(days=add_days)
        existing.meta = {**(existing.meta or {}), **(meta or {})}
        if paystack_reference and not existing.paystack_reference:
            existing.paystack_reference = paystack_reference
        await session.flush()
        return existing

    expires_at = now + timedelta(days=add_days)

    sub = Subscription(
        user_id=user.id,
        tier=tier_norm,
        status="active",
        started_at=now,
        expires_at=expires_at,
        paystack_reference=paystack_reference,
        meta=meta or {},
    )
    session.add(sub)
    await session.flush()
    return sub


async def expire_subscriptions(session: AsyncSession) -> int:
    """Mark active subscriptions as expired if past expiry."""
    now = datetime.utcnow()
    stmt = (
        update(Subscription)
        .where(
            Subscription.status == "active",
            Subscription.expires_at.is_not(None),
            Subscription.expires_at <= now,
        )
        .values(status="expired")
    )
    res = await session.execute(stmt)
    await session.flush()
    # SQLAlchemy typing doesn't guarantee rowcount; treat missing as 0.
    rowcount = getattr(res, "rowcount", None)
    return int(rowcount or 0)


async def persist_decision_log(
    signal_id: str | None,
    asset: str | None,
    timeframe: str | None,
    decision: str,
    reason: str | None = None,
    meta: dict | None = None,
) -> int:
    """Persist a decision/annotation about a signal or market evaluation.

    Returns inserted row id (when available) or 0.
    """
    try:
        async with get_session() as session:
            dl = DecisionLog(
                signal_id=signal_id,
                asset=asset,
                timeframe=timeframe,
                decision=decision,
                reason=reason,
                meta=meta or {},
            )
            session.add(dl)
            await session.flush()
            try:
                return int(dl.id or 0)
            except Exception:
                return 0
    except Exception as e:
        import logging
        logging.exception(f"Failed to persist decision log: {e}")
        return 0


async def persist_signal(signal_data: Dict[str, Any]) -> Optional[Signal]:
    """Persist a new signal to database."""
    try:
        async with get_session() as session:
            asset = str(signal_data.get("asset") or "").strip().upper()
            timeframe = str(signal_data.get("timeframe") or "").strip().lower()
            direction = str(signal_data.get("direction") or "").strip().lower()
            opposite = "short" if direction == "long" else ("long" if direction == "short" else "")
            if asset and timeframe and opposite:
                conflict_q = (
                    select(Signal.signal_id)
                    .outerjoin(Outcome, Outcome.signal_id == Signal.signal_id)
                    .where(
                        Signal.asset == asset,
                        Signal.timeframe == timeframe,
                        Signal.direction == opposite,
                        Signal.archived.is_(False),
                        (Outcome.id.is_(None) | Outcome.status.in_(ACTIVE_PARTIAL_OUTCOME_STATUSES)),
                    )
                    .limit(1)
                )
                existing_conflict = (await session.execute(conflict_q)).first()
                if existing_conflict:
                    return None
            # Convert take_profit list to JSON string
            tp_json = json.dumps(signal_data.get('take_profit', []))
            
            signal = Signal(
                asset=asset or signal_data.get('asset'),
                timeframe=timeframe or signal_data.get('timeframe'),
                direction=direction or signal_data.get('direction'),
                entry=signal_data.get('entry'),
                stop_loss=signal_data.get('stop_loss'),
                take_profit=tp_json,
                score=signal_data.get('score', 70),
                strategy_name=signal_data.get('strategy_name', 'unknown'),
                strategy_group=signal_data.get('strategy_group', 'mixed'),
                strength=signal_data.get('confidence', 0.7),
                ml_probability=signal_data.get('ml_probability'),
                fingerprint=f"{signal_data.get('asset')}_{signal_data.get('timeframe')}_{signal_data.get('direction')}_{int(signal_data.get('entry') or 0)}",
                created_at=datetime.utcnow(),
            )
            
            session.add(signal)
            await session.flush()
            return signal
    except Exception as e:
        import logging
        logging.error(f"Failed to persist signal: {e}")
        return None


def hash_api_token(raw_token: str) -> str:
    token = str(raw_token or "").strip()
    pepper = str(os.getenv("API_TOKEN_PEPPER") or "signalrankai-api-token-pepper")
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        token.encode("utf-8"),
        pepper.encode("utf-8"),
        600_000,
        dklen=32,
    )
    return dk.hex()


def token_prefix(raw_token: str) -> str:
    token = str(raw_token or "").strip()
    return token[:8]


async def create_api_token(
    session: AsyncSession,
    telegram_user_id: int,
    raw_token: str,
    *,
    scope: str = "signals:read",
    expires_at: datetime | None = None,
) -> ApiToken:
    user = await get_or_create_user(session, telegram_user_id=telegram_user_id)
    tok = ApiToken(
        user_id=user.id,
        token_hash=hash_api_token(raw_token),
        token_prefix=token_prefix(raw_token),
        scope=str(scope or "signals:read"),
        expires_at=expires_at,
        revoked_at=None,
    )
    session.add(tok)
    await session.flush()
    return tok


async def get_api_token_owner(
    session: AsyncSession,
    raw_token: str,
    *,
    required_scope: str = "signals:read",
) -> Optional[int]:
    now = datetime.utcnow()
    tok_hash = hash_api_token(raw_token)
    row = await session.execute(
        select(ApiToken, User.telegram_user_id)
        .join(User, User.id == ApiToken.user_id)
        .where(
            ApiToken.token_hash == tok_hash,
            ApiToken.revoked_at.is_(None),
            (ApiToken.expires_at.is_(None) | (ApiToken.expires_at > now)),
        )
        .limit(1)
    )
    found = row.first()
    if not found:
        return None
    api_token, telegram_user_id = found
    if required_scope and api_token.scope not in {required_scope, "signals:*", "*"}:
        return None
    api_token.last_used_at = now
    await session.flush()
    try:
        return int(telegram_user_id)
    except Exception:
        return None


async def revoke_api_token(
    session: AsyncSession,
    raw_token: str,
) -> int:
    now = datetime.utcnow()
    tok_hash = hash_api_token(raw_token)
    stmt = (
        update(ApiToken)
        .where(ApiToken.token_hash == tok_hash, ApiToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    res = await session.execute(stmt)
    await session.flush()
    return int(getattr(res, "rowcount", 0) or 0)


async def get_latest_active_api_token_meta(
    session: AsyncSession,
    telegram_user_id: int,
) -> Optional[dict]:
    now = datetime.utcnow()
    row = await session.execute(
        select(ApiToken.token_prefix, ApiToken.expires_at)
        .join(User, User.id == ApiToken.user_id)
        .where(
            User.telegram_user_id == int(telegram_user_id),
            ApiToken.revoked_at.is_(None),
            (ApiToken.expires_at.is_(None) | (ApiToken.expires_at > now)),
        )
        .order_by(ApiToken.created_at.desc())
        .limit(1)
    )
    found = row.first()
    if not found:
        return None
    return {
        "token_prefix": str(found[0] or ""),
        "expires_at": found[1].isoformat() if found[1] else None,
    }


def paystack_event_identity(event: Dict[str, Any], raw_body: bytes) -> tuple[str, str]:
    data = event.get("data") or {}
    event_type = str(event.get("event") or "").strip() or "unknown"
    explicit_id = str(event.get("id") or "").strip()
    reference = str(data.get("reference") or "").strip()
    if explicit_id:
        event_id = explicit_id
    elif reference:
        event_id = f"{event_type}:{reference}"
    else:
        customer_code = str((data.get("customer") or {}).get("customer_code") or "").strip()
        amount = str(data.get("amount") or "").strip()
        currency = str(data.get("currency") or "").strip()
        paid_at = str(data.get("paid_at") or data.get("created_at") or "").strip()
        stable = "|".join([event_type, customer_code, amount, currency, paid_at])
        event_id = f"{event_type}:{hashlib.sha256(stable.encode('utf-8')).hexdigest()[:24]}"
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    return event_id, payload_hash


async def mark_webhook_event_processed(
    session: AsyncSession,
    *,
    provider: str,
    event_id: str,
    event_type: str,
    reference: str | None,
    payload_hash: str,
    meta: Dict[str, Any] | None = None,
) -> bool:
    row = ProcessedWebhookEvent(
        provider=str(provider or "paystack"),
        event_id=str(event_id),
        event_type=str(event_type or "unknown"),
        reference=(str(reference).strip() or None) if reference is not None else None,
        payload_hash=str(payload_hash),
        meta=meta or {},
    )
    session.add(row)
    try:
        await session.flush()
        return True
    except IntegrityError:
        await session.rollback()
        return False
