"""Versioned read projection for fast, snapshot-first outcome callbacks."""

from __future__ import annotations

import html
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from core.signal_lifecycle import highest_tp_for_state, normalize_lifecycle_state

SNAPSHOT_VERSION = "phase4-pass4-v1"
_CACHE_PREFIX = "outcome_snapshot:v1:"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _parse_targets(raw: Any) -> list[float]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = [item.strip() for item in raw.split(",") if item.strip()]
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    values: list[float] = []
    for item in raw:
        try:
            if isinstance(item, dict):
                item = item.get("price") or item.get("tp") or item.get("target") or item.get("value")
            value = float(item)
            if value > 0:
                values.append(value)
        except Exception:
            continue
    return values


@dataclass(frozen=True, slots=True)
class OutcomeSnapshot:
    signal_id: str
    asset: str
    direction: str
    state: str
    highest_tp_hit: int
    price: float | None
    quote_time: str | None
    next_target: float | None
    expires_at: str | None
    provider: str
    provider_trusted: bool
    provider_reason: str | None
    updated_at: str
    source: str = "outcome_worker"
    version: str = SNAPSHOT_VERSION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "OutcomeSnapshot":
        if str(payload.get("version") or "") != SNAPSHOT_VERSION:
            raise ValueError("unsupported outcome snapshot version")
        return cls(
            signal_id=str(payload["signal_id"]),
            asset=str(payload.get("asset") or ""),
            direction=str(payload.get("direction") or ""),
            state=normalize_lifecycle_state(payload.get("state")),
            highest_tp_hit=max(0, int(payload.get("highest_tp_hit") or 0)),
            price=(float(payload["price"]) if payload.get("price") is not None else None),
            quote_time=_iso(payload.get("quote_time")),
            next_target=(float(payload["next_target"]) if payload.get("next_target") is not None else None),
            expires_at=_iso(payload.get("expires_at")),
            provider=str(payload.get("provider") or "unknown"),
            provider_trusted=bool(payload.get("provider_trusted")),
            provider_reason=(str(payload["provider_reason"]) if payload.get("provider_reason") else None),
            updated_at=str(payload.get("updated_at") or _utc_iso()),
            source=str(payload.get("source") or "outcome_worker"),
            version=SNAPSHOT_VERSION,
        )

    def is_stale(self, *, max_age_seconds: float | None = None) -> bool:
        threshold = float(
            max_age_seconds
            if max_age_seconds is not None
            else os.getenv("OUTCOME_SNAPSHOT_STALE_SECONDS", "90") or 90
        )
        try:
            updated = datetime.fromisoformat(self.updated_at.replace("Z", "+00:00"))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - updated).total_seconds() > max(1.0, threshold)
        except Exception:
            return True


def build_outcome_snapshot(
    signal: dict[str, Any],
    *,
    state: str,
    highest_tp_hit: int,
    price: float | None,
    quote_time: str | datetime | None,
    provider: str,
    provider_trusted: bool,
    provider_reason: str | None = None,
    source: str = "outcome_worker",
) -> OutcomeSnapshot:
    direction = str(signal.get("direction") or "long").lower()
    targets = _parse_targets(signal.get("take_profit"))
    targets = sorted(targets, reverse=direction == "short")
    highest = max(int(highest_tp_hit or 0), highest_tp_for_state(state))
    next_target = targets[highest] if highest < len(targets) else None
    return OutcomeSnapshot(
        signal_id=str(signal.get("signal_id") or ""),
        asset=str(signal.get("asset") or signal.get("symbol") or ""),
        direction=direction,
        state=normalize_lifecycle_state(state),
        highest_tp_hit=highest,
        price=float(price) if price is not None else None,
        quote_time=_iso(quote_time),
        next_target=float(next_target) if next_target is not None else None,
        expires_at=_iso(signal.get("expires_at")),
        provider=str(provider or "unknown"),
        provider_trusted=bool(provider_trusted),
        provider_reason=str(provider_reason) if provider_reason else None,
        updated_at=_utc_iso(),
        source=str(source),
    )


async def write_outcome_snapshot(snapshot: OutcomeSnapshot) -> bool:
    if not snapshot.signal_id:
        return False
    from core.redis_state import state

    ttl = max(30, int(os.getenv("OUTCOME_SNAPSHOT_TTL_SECONDS", "600") or 600))
    try:
        await state.cache_set(
            f"{_CACHE_PREFIX}{snapshot.signal_id}",
            json.dumps(snapshot.as_dict(), sort_keys=True, separators=(",", ":")),
            ex=ttl,
        )
        return True
    except Exception:
        return False


async def read_cached_outcome_snapshot(signal_id: str) -> OutcomeSnapshot | None:
    from core.redis_state import state

    try:
        raw = await state.cache_get(f"{_CACHE_PREFIX}{str(signal_id)}")
        if not raw:
            return None
        return OutcomeSnapshot.from_dict(json.loads(raw))
    except Exception:
        return None


async def read_outcome_snapshot(
    signal_id: str,
    *,
    db_fallback: bool = True,
) -> OutcomeSnapshot | None:
    cached = await read_cached_outcome_snapshot(signal_id)
    if cached is not None:
        return cached
    if not db_fallback:
        return None

    try:
        from db.models import Outcome, Signal, SignalLifecycle as LifecycleRow
        from db.priority import DBPriority
        from db.session import get_session
        from sqlalchemy import select

        async with get_session(priority=DBPriority.INTERACTIVE) as session:
            ref = str(signal_id).strip()
            stmt = select(Signal)
            if len(ref) >= 36:
                stmt = stmt.where(Signal.signal_id == ref)
            else:
                stmt = stmt.where(Signal.signal_id.ilike(f"{ref}%"))
            signal_row = (await session.execute(stmt.order_by(Signal.created_at.desc()).limit(1))).scalar_one_or_none()
            if signal_row is None:
                return None
            sid = str(signal_row.signal_id)
            lifecycle = (
                await session.execute(select(LifecycleRow).where(LifecycleRow.signal_id == sid).limit(1))
            ).scalar_one_or_none()
            outcome = (
                await session.execute(select(Outcome).where(Outcome.signal_id == sid).limit(1))
            ).scalar_one_or_none()

        state_value = normalize_lifecycle_state(
            getattr(lifecycle, "state", None) or getattr(outcome, "status", None)
        )
        outcome_meta = dict(getattr(outcome, "meta", None) or {})
        highest = max(
            highest_tp_for_state(state_value),
            int(outcome_meta.get("tp_hit_index") or 0),
        )
        signal_payload = {
            "signal_id": sid,
            "asset": signal_row.asset,
            "direction": signal_row.direction,
            "take_profit": signal_row.take_profit,
            "expires_at": signal_row.expires_at,
        }
        snapshot = build_outcome_snapshot(
            signal_payload,
            state=state_value,
            highest_tp_hit=highest,
            price=getattr(lifecycle, "last_price", None),
            quote_time=getattr(lifecycle, "last_checked_at", None),
            provider="database_projection",
            provider_trusted=False,
            provider_reason="snapshot_cache_miss",
            source="database_fallback",
        )
        await write_outcome_snapshot(snapshot)
        return snapshot
    except Exception:
        return None


def format_outcome_snapshot(snapshot: OutcomeSnapshot) -> str:
    state_label = snapshot.state.replace("_", " ").title()
    stale = snapshot.is_stale()
    freshness = "Last known snapshot" if stale else "Live outcome snapshot"
    price_line = (
        f"\nPrice: <code>{snapshot.price:.6g}</code>"
        if snapshot.price is not None
        else "\nPrice feed: temporarily unavailable"
    )
    next_line = (
        f"\nNext target: <code>{snapshot.next_target:.6g}</code>"
        if snapshot.next_target is not None
        else ""
    )
    trust_line = "" if snapshot.provider_trusted else "\nFeed confidence: awaiting a trusted refresh"
    highest_label = f"TP{snapshot.highest_tp_hit}" if snapshot.highest_tp_hit > 0 else "None yet"
    return (
        f"📊 <b>{html.escape(freshness)}</b>\n"
        f"Asset: <b>{html.escape(snapshot.asset)}</b>\n"
        f"Direction: <b>{html.escape(snapshot.direction.upper())}</b>\n"
        f"State: <b>{html.escape(state_label)}</b>\n"
        f"Highest target: <b>{highest_label}</b>"
        f"{price_line}{next_line}{trust_line}"
    )


__all__ = [
    "OutcomeSnapshot",
    "SNAPSHOT_VERSION",
    "build_outcome_snapshot",
    "format_outcome_snapshot",
    "read_cached_outcome_snapshot",
    "read_outcome_snapshot",
    "write_outcome_snapshot",
]
