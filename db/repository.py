from __future__ import annotations
from utils.timeutils import now_utc_naive

import os
import json
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from collections import deque

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from db.models import Subscription, User, Signal, Outcome, DecisionLog, ProcessedWebhookEvent, ApiToken
from db.session import get_session

if TYPE_CHECKING:
    from db.models import EconomicEvent

ACTIVE_PARTIAL_OUTCOME_STATUSES = ("tp1", "tp2")
_DECISION_LOG_RETRY_QUEUE: deque[dict[str, Any]] = deque(maxlen=5000)


def _env_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or str(default)).strip())
    except Exception:
        return default


async def count_active_subscriptions(
    session: AsyncSession,
) -> int:
    """Count ALL active subscriptions across all tiers."""
    now = now_utc_naive()
    q = (
        select(func.count(Subscription.id))
        .where(
            Subscription.status == "active",
            Subscription.expires_at.is_not(None),
            Subscription.expires_at > now,
        )
    )
    res = await session.execute(q)
    return int(res.scalar() or 0)


async def get_active_subscription(
    session: AsyncSession,
    telegram_user_id: int,
    tier: str,
) -> Optional[Subscription]:
    tier_norm = normalize_tier(tier)
    now = now_utc_naive()
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
    now = now_utc_naive()
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
    """Normalize customer subscription tiers without confusing them with roles."""
    t = (tier or "").strip().lower()
    if t in {"owner", "admin", "elite"}:
        return "vip"
    if t in {"institutional", "enterprise"}:
        return "institutional"
    if t in {"professional", "professional_monthly"}:
        return "professional"
    if t == "vip":
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
    telegram_user_id: int | None,
    tier: str,
    duration_days: int,
    paystack_reference: Optional[str],
    meta: Dict[str, Any],
    *,
    user_id: int | None = None,
) -> Subscription:
    # Legacy subscription-reference idempotency remains for older rows. New
    # webhook idempotency is enforced by payment_events, which permits each
    # renewal to keep its own provider reference without mutating this row.
    if paystack_reference:
        res = await session.execute(
            select(Subscription).where(Subscription.paystack_reference == paystack_reference)
        )
        existing = res.scalar_one_or_none()
        if existing is not None:
            return existing

    user: User | None = None
    if user_id is not None:
        user = (await session.execute(select(User).where(User.id == int(user_id)))).scalar_one_or_none()
        if user is None:
            raise ValueError("canonical_user_not_found")
        if telegram_user_id is not None and user.telegram_user_id not in {None, int(telegram_user_id)}:
            raise ValueError("canonical_and_telegram_identity_mismatch")
    elif telegram_user_id is not None:
        user = await get_or_create_user(session, int(telegram_user_id))
    else:
        raise ValueError("subscription_user_identity_required")

    now = now_utc_naive()
    tier_norm = normalize_tier(tier)
    add_days = max(int(duration_days), 1)

    tier_order = {"free": 0, "premium": 1, "vip": 2, "professional": 3, "institutional": 4}
    active_rows = list((await session.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.status == "active",
            Subscription.expires_at.is_not(None),
            Subscription.expires_at > now,
        )
        .order_by(Subscription.expires_at.desc())
        .with_for_update()
    )).scalars().all())
    highest = max(active_rows, key=lambda row: tier_order.get(normalize_tier(row.tier), 0), default=None)
    purchased_rank = tier_order.get(tier_norm, 0)
    highest_rank = tier_order.get(normalize_tier(highest.tier), 0) if highest is not None else -1

    if highest is not None and highest_rank >= purchased_rank:
        # Same-tier renewal extends normally. A lower-tier purchase can never
        # downgrade an active higher entitlement; it extends that entitlement.
        base = max(highest.expires_at or now, now)
        highest.expires_at = base + timedelta(days=add_days)
        highest.meta = {
            **(highest.meta or {}),
            **(meta or {}),
            "last_purchase_tier": tier_norm,
            "lower_tier_purchase_preserved_higher_access": highest_rank > purchased_rank,
        }
        user.tier = normalize_tier(highest.tier)
        user.premium_until = highest.expires_at
        await session.flush()
        return highest

    if highest is not None and purchased_rank > highest_rank:
        for row in active_rows:
            row.status = "superseded"
            row.meta = {**(row.meta or {}), "superseded_by_tier": tier_norm, "superseded_at": now.isoformat()}

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
    user.tier = tier_norm
    user.premium_until = expires_at
    await session.flush()
    return sub


async def expire_subscriptions(session: AsyncSession) -> int:
    """Mark active subscriptions as expired if past expiry."""
    now = now_utc_naive()
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
    
    IMPORTANT: With NullPool enabled, failing to commit causes data loss!
    """
    if str(os.getenv("DECISION_LOG_WRITE_ENABLED", "1") or "1").strip().lower() not in {
        "1", "true", "yes", "on",
    }:
        return 0
    try:
        async with get_session(priority="background", label="db_repository") as session:
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
            
            # FIX: Explicit commit for NullPool compatibility (data vanishes without commit!)
            await session.commit()
            
            try:
                return int(dl.id or 0)
            except Exception:
                return 0
    except Exception as e:
        import logging
        if type(e).__name__ == "NoncriticalWriteDropped":
            _DECISION_LOG_RETRY_QUEUE.append({
                "signal_id": signal_id,
                "asset": asset,
                "timeframe": timeframe,
                "decision": decision,
                "reason": reason,
                "meta": dict(meta or {}),
            })
            logging.getLogger(__name__).info(
                "Decision log queued because DB gate is busy pending=%s",
                len(_DECISION_LOG_RETRY_QUEUE),
            )
        else:
            logging.exception(f"Failed to persist decision log: {e}")
        return 0


async def persist_decision_logs_batch(rows: list[dict[str, Any]]) -> int:
    """Persist one bounded market-scan batch in a single background transaction."""
    if str(os.getenv("DECISION_LOG_WRITE_ENABLED", "1") or "1").strip().lower() not in {
        "1", "true", "yes", "on",
    }:
        return 0
    clean = []
    for row in list(rows or [])[:100]:
        clean.append({
            "signal_id": row.get("signal_id"), "asset": row.get("asset"),
            "timeframe": row.get("timeframe"), "decision": str(row.get("decision") or "observed")[:32],
            "reason": str(row.get("reason") or "")[:1000] or None, "meta": dict(row.get("meta") or {}),
        })
    if not clean:
        return 0
    try:
        async with get_session(priority="background", label="decision_log_market_batch") as session:
            session.add_all([DecisionLog(**item) for item in clean])
            await session.commit()
        return len(clean)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Market decision-log batch failed: %s", type(exc).__name__)
        return 0


async def flush_decision_log_retry_queue(limit: int = 100) -> int:
    """Best-effort bounded flush for decision annotations deferred by DB admission."""
    if not _DECISION_LOG_RETRY_QUEUE:
        return 0
    batch: list[dict[str, Any]] = []
    for _ in range(min(max(1, int(limit)), len(_DECISION_LOG_RETRY_QUEUE))):
        batch.append(_DECISION_LOG_RETRY_QUEUE.popleft())
    try:
        async with get_session(priority="background", label="decision_log_retry", timeout_seconds=2.0) as session:
            session.add_all([DecisionLog(**item) for item in batch])
            await session.commit()
        return len(batch)
    except Exception:
        for item in reversed(batch):
            _DECISION_LOG_RETRY_QUEUE.appendleft(item)
        return 0


async def persist_signal(signal_data: Dict[str, Any]) -> Optional[Signal]:
    """Persist a new signal to database."""
    try:
        async with get_session() as session:
            asset = str(signal_data.get("asset") or "").strip().upper()
            timeframe = str(signal_data.get("timeframe") or "").strip().lower()
            from core.production_integrity import (
                canonical_direction,
                semantic_entries_equivalent,
                signal_thesis_fingerprint,
                signal_thesis_scope,
            )
            direction = canonical_direction(signal_data.get("direction"))
            thesis_fingerprint = signal_thesis_fingerprint(signal_data)
            # Serialize duplicate-thesis admission across engine replicas. This
            # closes the race where two workers both observe no recent signal and
            # persist near-identical BTC/SOL ideas seconds apart.
            try:
                if str(session.get_bind().dialect.name or "").lower() == "postgresql":
                    semantic_scope = f"signal-thesis:{signal_thesis_scope(signal_data)}"
                    await session.execute(
                        text("SELECT pg_advisory_xact_lock(hashtext(:fingerprint))"),
                        {"fingerprint": thesis_fingerprint},
                    )
                    await session.execute(
                        text("SELECT pg_advisory_xact_lock(hashtext(:scope))"),
                        {"scope": semantic_scope},
                    )
            except Exception as lock_error:
                from core.env import runtime_environment_name
                if runtime_environment_name("development") == "production":
                    raise RuntimeError("signal_thesis_lock_unavailable") from lock_error
                # Non-production SQLite/test environments still receive the
                # deterministic recent-thesis query below.
            thesis_cutoff = now_utc_naive() - timedelta(
                hours=max(1, _env_int("SIGNAL_THESIS_DEDUP_HOURS", 4))
            )
            recent_thesis = (await session.execute(
                select(Signal.signal_id).where(
                    Signal.thesis_fingerprint == thesis_fingerprint,
                    Signal.created_at >= thesis_cutoff,
                    Signal.archived.is_(False),
                    Signal.expired.is_(False),
                ).limit(1)
            )).scalar_one_or_none()
            if recent_thesis is not None:
                return None
            try:
                semantic_tolerance = max(0.0001, min(0.05, float(
                    os.getenv("SIGNAL_SEMANTIC_ENTRY_TOLERANCE_PCT", "0.003") or 0.003
                )))
            except Exception:
                semantic_tolerance = 0.003
            strategy_name = str(signal_data.get("strategy_name") or signal_data.get("strategy") or "unknown").lower().strip()
            semantic_candidates = (await session.execute(
                select(Signal).where(
                    Signal.asset == asset,
                    Signal.direction == direction,
                    func.lower(Signal.strategy_name) == strategy_name,
                    Signal.created_at >= thesis_cutoff,
                    Signal.archived.is_(False),
                    Signal.expired.is_(False),
                ).order_by(Signal.created_at.desc())
            )).scalars().all()
            entry_value = float(signal_data.get("entry") or 0)
            for candidate in semantic_candidates:
                if semantic_entries_equivalent(
                    getattr(candidate, "entry", None),
                    entry_value,
                    tolerance=semantic_tolerance,
                ):
                    return None
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
            
            calibrated_probability = signal_data.get("ml_probability_calibrated")
            calibration_version = signal_data.get("ml_calibration_version")
            signal = Signal(
                asset=asset or signal_data.get('asset'),
                timeframe=timeframe or signal_data.get('timeframe'),
                direction=direction or signal_data.get('direction'),
                entry=signal_data.get('entry'),
                stop_loss=signal_data.get('stop_loss'),
                take_profit=tp_json,
                status=signal_data.get('status', 'issued'),
                score=signal_data.get('score', 70),
                strategy_name=signal_data.get('strategy_name', 'unknown'),
                strategy_group=signal_data.get('strategy_group', 'mixed'),
                strength=signal_data.get('confidence', 0.7),
                ml_probability=calibrated_probability if calibrated_probability is not None else signal_data.get('ml_probability'),
                ml_probability_raw=signal_data.get('ml_probability_raw') or signal_data.get('ml_probability'),
                ml_probability_calibrated=calibrated_probability,
                ml_calibration_version=calibration_version,
                ml_calibration_validated=bool(signal_data.get('ml_calibration_validated', False)),
                ml_calibration_validation_rows=(
                    int(signal_data.get('ml_calibration_validation_rows'))
                    if signal_data.get('ml_calibration_validation_rows') is not None
                    else None
                ),
                ml_calibration_brier=(
                    float(signal_data.get('ml_calibration_brier'))
                    if signal_data.get('ml_calibration_brier') is not None
                    else None
                ),
                ml_calibration_ece=(
                    float(signal_data.get('ml_calibration_ece'))
                    if signal_data.get('ml_calibration_ece') is not None
                    else None
                ),
                fingerprint=thesis_fingerprint,
                thesis_fingerprint=thesis_fingerprint,
                asset_discovery_provider=(str(signal_data.get("asset_discovery_provider") or "").strip()[:128] or None),
                quality_gate_version=str(signal_data.get('quality_gate_version') or 'production-integrity-v1'),
                quality_gate_passed=bool(signal_data.get('quality_gate_passed', False)),
                created_at=now_utc_naive(),
            )
            
            session.add(signal)
            await session.flush()

            # Persist structured adaptive evidence and canonical sequence references
            # in the same short transaction. Unknown/legacy signals remain unaffected.
            if signal_data.get("adaptive_evidence") or signal_data.get("adaptive_sequence_refs"):
                try:
                    from engine.adaptive.repository import persist_signal_adaptive_evidence
                    await persist_signal_adaptive_evidence(session, signal, signal_data)
                except Exception as adaptive_error:
                    import logging
                    logging.getLogger(__name__).warning(
                        "[adaptive] evidence persistence skipped signal=%s error=%s",
                        getattr(signal, "signal_id", None), adaptive_error,
                    )
            
            # FIX: Explicit commit for NullPool compatibility
            await session.commit()
            
            return signal
    except Exception as e:
        import logging
        logging.error(f"Failed to persist signal: {e}")
        return None


def hash_api_token(raw_token: str) -> str:
    token = str(raw_token or "").strip()
    from core.security import api_token_pepper

    pepper = api_token_pepper()
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
    now = now_utc_naive()
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
    now = now_utc_naive()
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
    now = now_utc_naive()
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
        status="pending",
        attempt_count=0,
        updated_at=now_utc_naive(),
        meta=meta or {},
    )
    session.add(row)
    try:
        await session.flush()
        return True
    except IntegrityError:
        await session.rollback()
        return False


async def get_webhook_event(session: AsyncSession, event_id: str) -> ProcessedWebhookEvent | None:
    return (
        await session.execute(
            select(ProcessedWebhookEvent).where(ProcessedWebhookEvent.event_id == str(event_id))
        )
    ).scalar_one_or_none()


async def update_webhook_event_status(
    session: AsyncSession,
    *,
    event_id: str,
    status: str,
    error: str | None = None,
    increment_attempt: bool = False,
) -> ProcessedWebhookEvent | None:
    row = (
        await session.execute(
            select(ProcessedWebhookEvent)
            .where(ProcessedWebhookEvent.event_id == str(event_id))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    row.status = str(status or "failed")[:16]
    if increment_attempt:
        row.attempt_count = int(row.attempt_count or 0) + 1
    row.last_error = str(error)[:512] if error else None
    row.updated_at = now_utc_naive()
    if row.status in {"succeeded", "ignored"}:
        row.processed_at = now_utc_naive()
    await session.flush()
    return row


async def list_recoverable_webhook_events(
    session: AsyncSession,
    *,
    provider: str = "paystack",
    max_attempts: int = 10,
    limit: int = 50,
) -> list[ProcessedWebhookEvent]:
    rows = await session.execute(
        select(ProcessedWebhookEvent)
        .where(
            ProcessedWebhookEvent.provider == str(provider),
            ProcessedWebhookEvent.status.in_(("pending", "failed", "processing")),
            ProcessedWebhookEvent.attempt_count < max(1, int(max_attempts)),
        )
        .order_by(ProcessedWebhookEvent.updated_at.asc(), ProcessedWebhookEvent.id.asc())
        .limit(max(1, min(int(limit), 200)))
    )
    return list(rows.scalars().all())


async def get_economic_events(session, hours_ahead: int = 168) -> List["EconomicEvent"]:
    """Get upcoming medium/high-impact economic events from DB."""
    from db.models import EconomicEvent

    now = now_utc_naive()
    window_end = now + timedelta(hours=max(0, int(hours_ahead or 0)))
    try:
        result = await session.execute(
            select(EconomicEvent)
            .where(
                EconomicEvent.event_date >= now,
                EconomicEvent.event_date <= window_end,
                EconomicEvent.impact.in_(["high", "medium"]),
            )
            .order_by(EconomicEvent.event_date)
        )
        return list(result.scalars().all())
    except Exception:
        return []
