"""Canonical web signal fan-out.

The website is a real delivery channel, but Telegram delivery proof remains
Telegram-specific.  This module therefore writes idempotent web receipts to
notification_events after the same profile, quota, cooldown, quality,
freshness, quote-trust and risk gates used for live delivery.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select, text

from core.tier_policy import get_entitlements
from db.models import Signal, User
from db.session import get_session
from utils.timeutils import now_utc_naive


@dataclass(frozen=True, slots=True)
class WebFanoutResult:
    examined_signals: int = 0
    eligible_users: int = 0
    delivered: int = 0
    duplicates: int = 0
    blocked_profile: int = 0
    blocked_quality: int = 0
    blocked_entitlement: int = 0
    blocked_delay: int = 0
    blocked_quota: int = 0
    blocked_cooldown: int = 0
    blocked_freshness: int = 0
    quote_failures: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "examined_signals": self.examined_signals,
            "eligible_users": self.eligible_users,
            "delivered": self.delivered,
            "duplicates": self.duplicates,
            "blocked_profile": self.blocked_profile,
            "blocked_quality": self.blocked_quality,
            "blocked_entitlement": self.blocked_entitlement,
            "blocked_delay": self.blocked_delay,
            "blocked_quota": self.blocked_quota,
            "blocked_cooldown": self.blocked_cooldown,
            "blocked_freshness": self.blocked_freshness,
            "quote_failures": self.quote_failures,
        }


def _signal_payload(signal: Signal) -> dict[str, Any]:
    return {
        column.key: getattr(signal, column.key, None)
        for column in signal.__table__.columns
    }


def _normalized_asset_class(signal: dict[str, Any]) -> str:
    raw = str(signal.get("asset_class") or "").strip().lower()
    aliases = {
        "forex": "fx",
        "equity": "stock",
        "equities": "stock",
        "indices": "index",
        "commodities": "commodity",
    }
    if raw:
        return aliases.get(raw, raw)
    try:
        from services.asset_mapper import classify_asset

        inferred = str(
            classify_asset(str(signal.get("asset") or signal.get("symbol") or ""))
            or ""
        ).strip().lower()
        return aliases.get(inferred, inferred)
    except Exception:
        return ""


def _signal_age_minutes(signal: dict[str, Any], now: datetime) -> float:
    raw = signal.get("created_at") or signal.get("generated_at")
    if not isinstance(raw, datetime):
        return float("inf")
    created = raw.astimezone(timezone.utc).replace(tzinfo=None) if raw.tzinfo else raw
    return max(0.0, (now - created).total_seconds() / 60.0)


def _notification_id(user_id: int, signal_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"signalrank:web-signal:{int(user_id)}:{signal_id}"))


def _cycle_limit(tier: str) -> int:
    defaults = {
        "free": 1,
        "premium": 1,
        "vip": 2,
        "professional": 3,
        "institutional": 5,
        "admin": 5,
        "owner": 10,
    }
    name = f"WEB_SIGNAL_PER_CYCLE_{str(tier or 'free').upper()}"
    try:
        return max(1, min(25, int(os.getenv(name, str(defaults.get(str(tier).lower(), 1))) or 1)))
    except Exception:
        return defaults.get(str(tier).lower(), 1)


async def _daily_distinct_count(session, user_id: int, start: datetime) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT COUNT(DISTINCT signal_id)
                FROM (
                    SELECT sd.signal_id::text AS signal_id
                    FROM signal_deliveries sd
                    WHERE sd.user_id=:uid
                      AND sd.sent_ok IS TRUE
                      AND sd.delivered_at >= :start
                    UNION ALL
                    SELECT ne.channel_data->>'signal_id' AS signal_id
                    FROM notification_events ne
                    WHERE ne.user_id=:uid
                      AND ne.event_type='signal'
                      AND ne.created_at >= :start
                      AND COALESCE(ne.channel_data->>'signal_id','') <> ''
                ) delivered
                """
            ),
            {"uid": int(user_id), "start": start},
        )
    ).scalar_one_or_none()
    return int(row or 0)


async def _recent_assets(session, user_id: int, cutoff: datetime) -> set[str]:
    rows = (
        await session.execute(
            text(
                """
                SELECT DISTINCT UPPER(COALESCE(s.asset,'')) AS asset
                FROM signals s
                JOIN (
                    SELECT sd.signal_id::text AS signal_id, sd.delivered_at AS occurred_at
                    FROM signal_deliveries sd
                    WHERE sd.user_id=:uid AND sd.sent_ok IS TRUE
                    UNION ALL
                    SELECT ne.channel_data->>'signal_id' AS signal_id, ne.created_at AS occurred_at
                    FROM notification_events ne
                    WHERE ne.user_id=:uid
                      AND ne.event_type='signal'
                      AND COALESCE(ne.channel_data->>'signal_id','') <> ''
                ) receipt ON receipt.signal_id=s.signal_id
                WHERE receipt.occurred_at >= :cutoff
                """
            ),
            {"uid": int(user_id), "cutoff": cutoff},
        )
    ).all()
    return {str(row[0] or "").upper().strip() for row in rows if row and row[0]}


async def _snapshot_candidates() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from db.access import resolve_product_tier
    from services.user_intelligence import (
        get_platform_user_trading_preferences,
        preferences_to_payload,
    )

    now = now_utc_naive()
    lookback_seconds = max(
        120,
        min(1800, int(os.getenv("WEB_SIGNAL_FANOUT_LOOKBACK_SECONDS", "600") or 600)),
    )
    cutoff = now - timedelta(seconds=lookback_seconds)
    signal_limit = max(
        1,
        min(100, int(os.getenv("WEB_SIGNAL_FANOUT_SIGNAL_LIMIT", "30") or 30)),
    )

    async with get_session(
        priority="interactive",
        label="platform.web_signal_fanout.snapshot",
        timeout_seconds=max(
            3.0,
            min(
                20.0,
                float(
                    os.getenv("WEB_SIGNAL_FANOUT_DB_WAIT_SECONDS", "8")
                    or 8
                ),
            ),
        ),
        drop_if_busy=False,
    ) as session:
        signal_rows = list(
            (
                await session.execute(
                    select(Signal)
                    .where(
                        Signal.created_at >= cutoff,
                        Signal.expired.is_(False),
                        Signal.archived.is_(False),
                        func.lower(func.coalesce(Signal.status, "active")).in_(
                            ("active", "open", "issued")
                        ),
                    )
                    .order_by(Signal.created_at.desc())
                    .limit(signal_limit)
                )
            ).scalars().all()
        )
        user_rows = list(
            (
                await session.execute(
                    select(User)
                    .where(
                        User.is_blocked.is_(False),
                        User.is_suspended.is_(False),
                        text(
                            "COALESCE((SELECT np.web_enabled FROM notification_preferences np "
                            "WHERE np.user_id=users.id), TRUE) IS TRUE"
                        ),
                    )
                    .order_by(User.id)
                    .limit(
                        max(
                            1,
                            min(
                                1000,
                                int(os.getenv("WEB_SIGNAL_FANOUT_USER_LIMIT", "250") or 250),
                            ),
                        )
                    )
                )
            ).scalars().all()
        )

        users: list[dict[str, Any]] = []
        for user in user_rows:
            if not bool(getattr(user, "accepted_terms", False)):
                continue
            tier = str(await resolve_product_tier(session, user) or "free").strip().lower()
            policy = get_entitlements(tier)
            prefs = await get_platform_user_trading_preferences(session, int(user.id))
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            delivered_today = await _daily_distinct_count(session, int(user.id), day_start)
            cooldown_hours = max(
                0.0,
                float(
                    os.getenv(
                        f"{tier.upper()}_ASSET_COOLDOWN_HOURS",
                        os.getenv("ASSET_REPEAT_LOCK_HOURS", "4"),
                    )
                    or 4
                ),
            )
            locked_assets = await _recent_assets(
                session,
                int(user.id),
                now - timedelta(hours=cooldown_hours),
            )
            users.append(
                {
                    "id": int(user.id),
                    "tier": tier,
                    "minimum_signal_score": float(policy.minimum_signal_score),
                    "daily_limit": float(policy.daily_signal_limit),
                    "delivery_delay_minutes": int(policy.delivery_delay_minutes),
                    "allowed_asset_classes": tuple(policy.allowed_asset_classes),
                    "delivered_today": delivered_today,
                    "locked_assets": locked_assets,
                    "preferences": preferences_to_payload(prefs),
                    "per_cycle_limit": _cycle_limit(tier),
                }
            )
        await session.rollback()

    return [_signal_payload(signal) for signal in signal_rows], users


async def deliver_recent_web_signals() -> dict[str, int]:
    """Create idempotent website receipts for newly generated eligible signals."""
    from core.signal_quality_gate import evaluate_signal_quality
    from data.get_live_price import get_live_price_result
    from data.provider_types import LivePriceQuote
    from engine.delivery_freshness import validate_delivery_freshness
    from services.user_intelligence import preferences_from_payload, signal_matches_preferences

    signals, users = await _snapshot_candidates()
    counters = {
        "examined_signals": len(signals),
        "eligible_users": len(users),
        "delivered": 0,
        "duplicates": 0,
        "blocked_profile": 0,
        "blocked_quality": 0,
        "blocked_entitlement": 0,
        "blocked_delay": 0,
        "blocked_quota": 0,
        "blocked_cooldown": 0,
        "blocked_freshness": 0,
        "quote_failures": 0,
    }
    if not signals or not users:
        return counters

    per_user_sent: dict[int, int] = {int(user["id"]): 0 for user in users}
    pending: list[dict[str, Any]] = []

    for signal in signals:
        signal_id = str(signal.get("signal_id") or "").strip()
        symbol = str(signal.get("asset") or signal.get("symbol") or "").strip().upper()
        if not signal_id or not symbol:
            continue

        quote = await get_live_price_result(
            symbol,
            timeout=max(
                2.0,
                min(
                    10.0,
                    float(os.getenv("WEB_SIGNAL_FINAL_QUOTE_TIMEOUT_SECONDS", "5") or 5),
                ),
            ),
            require_delivery_freshness=True,
        )
        if not isinstance(quote, LivePriceQuote):
            counters["quote_failures"] += 1
            continue

        quality = evaluate_signal_quality(signal)
        if not bool(signal.get("quality_gate_passed")) or not quality.ok:
            counters["blocked_quality"] += len(users)
            continue

        signal_class = _normalized_asset_class(signal)
        signal_age_minutes = _signal_age_minutes(signal, now_utc_naive())
        for user in users:
            uid = int(user["id"])
            if signal_class and signal_class not in set(user["allowed_asset_classes"]):
                counters["blocked_entitlement"] += 1
                continue
            if signal_age_minutes < float(user["delivery_delay_minutes"]):
                counters["blocked_delay"] += 1
                continue
            if per_user_sent[uid] >= int(user["per_cycle_limit"]):
                continue
            daily_limit = float(user["daily_limit"])
            delivered_today = int(user["delivered_today"]) + per_user_sent[uid]
            if math.isfinite(daily_limit) and delivered_today >= int(daily_limit):
                counters["blocked_quota"] += 1
                continue
            if float(signal.get("score") or 0.0) < float(user["minimum_signal_score"]):
                counters["blocked_quality"] += 1
                continue
            if symbol in set(user["locked_assets"]):
                counters["blocked_cooldown"] += 1
                continue

            prefs = preferences_from_payload(dict(user["preferences"]))
            matches, _reason = signal_matches_preferences(signal, prefs)
            if not matches:
                counters["blocked_profile"] += 1
                continue

            fresh = await validate_delivery_freshness(
                signal,
                user_profile=str(prefs.trade_profile or ""),
                live_quote=quote,
                final_send=True,
                delivery_tier=str(user["tier"]),
            )
            if not fresh.ok:
                counters["blocked_freshness"] += 1
                continue

            pending.append(
                {
                    "notification_id": _notification_id(uid, signal_id),
                    "user_id": uid,
                    "signal_id": signal_id,
                    "asset": symbol,
                    "title": f"{symbol} {str(signal.get('direction') or '').upper()} signal",
                    "body": (
                        f"{signal.get('timeframe') or ''} · "
                        f"score {float(signal.get('score') or 0):.1f} · "
                        "Open SignalRankAI for the validated levels and live status."
                    ),
                    "channel_data": {
                        "channel": "web",
                        "surface": "signal_feed",
                        "signal_id": signal_id,
                        "tier": str(user["tier"]),
                        "quote_provider": fresh.quote_provider,
                        "quote_kind": fresh.quote_kind,
                        "quote_source_timestamp": fresh.quote_source_timestamp,
                        "quote_source_age_seconds": fresh.quote_source_age_seconds,
                        "entry_drift_pct": fresh.entry_drift_pct,
                        "queue_age_seconds": fresh.queue_age_seconds,
                        "policy_version": fresh.policy_version,
                        "rule_results": list(fresh.rule_results or ()),
                    },
                }
            )
            per_user_sent[uid] += 1
            user["locked_assets"].add(symbol)

    if not pending:
        return counters

    async with get_session(
        priority="interactive",
        label="platform.web_signal_fanout.persist",
        timeout_seconds=12.0,
        drop_if_busy=False,
    ) as session:
        for item in pending:
            result = await session.execute(
                text(
                    """
                    INSERT INTO notification_events(
                        notification_id,user_id,event_type,title,body,severity,
                        channel_data,created_at
                    )
                    VALUES(
                        :notification_id,:user_id,'signal',:title,:body,'info',
                        CAST(:channel_data AS JSONB),NOW()
                    )
                    ON CONFLICT(notification_id) DO NOTHING
                    """
                ),
                {
                    "notification_id": item["notification_id"],
                    "user_id": item["user_id"],
                    "title": item["title"][:200],
                    "body": item["body"],
                    "channel_data": __import__("json").dumps(
                        item["channel_data"],
                        separators=(",", ":"),
                        default=str,
                    ),
                },
            )
            if int(result.rowcount or 0) == 1:
                counters["delivered"] += 1
            else:
                counters["duplicates"] += 1
        await session.commit()

    return counters


__all__ = ["WebFanoutResult", "deliver_recent_web_signals"]
