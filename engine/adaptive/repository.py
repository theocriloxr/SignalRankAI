from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from core.redis_state import state
from db.session import get_session
from .lifecycle import approval_lease, lock_profile_lifecycle, health_interval_seconds
from .market_input import MarketInputSnapshot, persist_market_inputs, restore_market_input

logger = logging.getLogger(__name__)


async def persist_optional_signal_evidence(session: AsyncSession, signal: Any, payload: Mapping[str, Any]) -> None:
    """Keep optional research writes atomic without poisoning signal storage."""
    if not (payload.get("adaptive_evidence") or payload.get("adaptive_sequence_refs")):
        return
    try:
        async with session.begin_nested():
            await persist_signal_adaptive_evidence(session, signal, payload)
    except Exception as error:
        logger.warning("[adaptive] evidence persistence skipped signal=%s error_type=%s",
                       getattr(signal, "signal_id", None), type(error).__name__)


def _health_receipt_fresh(checked: Any) -> bool:
    if not isinstance(checked, datetime):
        return False
    instant = checked.astimezone(timezone.utc).replace(tzinfo=None) if checked.tzinfo else checked
    age = (datetime.now(timezone.utc).replace(tzinfo=None) - instant).total_seconds()
    return -5 <= age <= 2 * health_interval_seconds() + 30


async def persist_signal_adaptive_evidence(session: AsyncSession, signal: Any, payload: Mapping[str, Any]) -> None:
    evidence = list(payload.get("adaptive_evidence") or [])[:16]
    refs = list(payload.get("adaptive_sequence_refs") or [])[:8]
    captures = payload.get("_adaptive_input_snapshots") or []
    if not isinstance(captures, (list, tuple)) or len(captures) > 8:
        raise ValueError("market_input_capture_batch_budget_exceeded")
    snapshots = []
    captured_by_hash = {}
    for item in captures:
        if not isinstance(item, Mapping):
            raise ValueError("market_input_capture_invalid")
        digest, stored = item["content_hash"], item["payload"]
        context = restore_market_input(stored, content_hash=digest)
        if context.asset != signal.asset:
            raise ValueError("market_input_signal_asset_mismatch")
        encoded = json.dumps(stored, sort_keys=True, separators=(",", ":"), allow_nan=False)
        captured_at = datetime.fromisoformat(stored["captured_at"])
        snapshots.append(MarketInputSnapshot(digest, encoded, len(context.candles), captured_at))
        captured_by_hash[digest] = context
    for ref in refs:
        digest = (ref.get("summary") or {}).get("market_input_hash")
        if digest is not None and (digest not in captured_by_hash
            or captured_by_hash[digest].timeframe != ref.get("timeframe")):
            raise ValueError("market_input_reference_capture_missing_or_mismatched")
        if digest is not None:
            stored = next(item["payload"] for item in captures if item["content_hash"] == digest)
            if (ref.get("summary") or {}).get("universe_observation_hash") != (stored.get("universe_observation") or {}).get("content_hash"):
                raise ValueError("market_input_universe_reference_mismatch")
    await persist_market_inputs(session, snapshots)
    for item in evidence:
        await session.execute(
            text(
                """INSERT INTO adaptive_signal_evidence(signal_id,asset,timeframe,strategy_id,strategy_version,family,direction,setup_type,confidence,raw_score,evidence_quality,profile_id,profile_version,regime,data_quality,evidence,conflicts,duplicate_fingerprint,created_at) VALUES(:signal_id,:asset,:timeframe,:strategy_id,:strategy_version,:family,:direction,:setup_type,:confidence,:raw_score,:evidence_quality,:profile_id,:profile_version,:regime,CAST(:data_quality AS JSONB),CAST(:evidence AS JSONB),CAST(:conflicts AS JSONB),:duplicate_fingerprint,NOW()) ON CONFLICT(signal_id,duplicate_fingerprint) DO NOTHING"""
            ),
            {
                "signal_id": signal.signal_id,
                "asset": signal.asset,
                "timeframe": str(item.get("timeframe") or signal.timeframe),
                "strategy_id": str(item.get("strategy_id") or "unknown")[:128],
                "strategy_version": str(item.get("strategy_version") or "unknown")[:64],
                "family": str(item.get("family") or "unknown")[:64],
                "direction": str(item.get("direction") or signal.direction)[:16],
                "setup_type": str(item.get("setup_type") or "unknown")[:128],
                "confidence": float(item.get("confidence") or 0.0),
                "raw_score": float(item.get("raw_score") or 0.0),
                "evidence_quality": str(item.get("evidence_quality") or "genuine")[:24],
                "profile_id": str(payload.get("adaptive_profile_id") or "")[:128] or None,
                "profile_version": int(payload.get("adaptive_profile_version") or 0) or None,
                "regime": str(payload.get("regime") or signal.regime or "unknown")[:32],
                "data_quality": json.dumps(item.get("data_quality") or {}),
                "evidence": json.dumps(item.get("evidence") or {}),
                "conflicts": json.dumps(item.get("conflicts") or []),
                "duplicate_fingerprint": str(item.get("duplicate_fingerprint") or "")[:64],
            },
        )
    for ref in refs:
        await session.execute(
            text(
                """INSERT INTO adaptive_signal_sequences(signal_id,asset,timeframe,sequence_hash,candle_count,start_time_ms,end_time_ms,provider,evidence_stage,summary,created_at) VALUES(:signal_id,:asset,:timeframe,:sequence_hash,:candle_count,:start_time_ms,:end_time_ms,:provider,:evidence_stage,CAST(:summary AS JSONB),NOW()) ON CONFLICT(signal_id,timeframe,evidence_stage,sequence_hash) DO NOTHING"""
            ),
            {
                "signal_id": signal.signal_id,
                "asset": signal.asset,
                "timeframe": str(ref.get("timeframe") or signal.timeframe),
                "sequence_hash": str(ref.get("sequence_hash") or "")[:64],
                "candle_count": int(ref.get("candle_count") or 0),
                "start_time_ms": ref.get("start_time_ms"),
                "end_time_ms": ref.get("end_time_ms"),
                "provider": str(ref.get("provider") or "unknown")[:64],
                "evidence_stage": str(ref.get("evidence_stage") or "pre_signal")[:24],
                "summary": json.dumps(ref.get("summary") or {}),
            },
        )


async def publish_approved_profiles() -> int:
    from .health_baselines import baseline_valid
    published = 0
    async with get_session(
        priority="background",
        label="adaptive.publish_profiles",
        timeout_seconds=float(os.getenv("ADAPTIVE_DB_TIMEOUT_SECONDS", "4") or 4),
    ) as session:
        await lock_profile_lifecycle(session)
        rows = (
            (
                await session.execute(
                    text(
                        """SELECT p.*,to_jsonb(b) AS approved_health_baseline,h.report AS health_report,h.created_at AS health_checked_at
                        FROM adaptive_asset_profiles p
                        LEFT JOIN strategy_health_baselines b ON b.profile_id=p.profile_id
                        LEFT JOIN LATERAL (SELECT report,created_at FROM strategy_health_events e
                            WHERE e.profile_id=p.profile_id AND e.baseline_id=b.baseline_id
                            ORDER BY event_id DESC LIMIT 1) h ON TRUE
                        WHERE p.state IN ('APPROVED','LIMITED_LIVE','CANARY') AND p.is_current=TRUE"""
                    )
                )
            )
            .mappings()
            .all()
        )
        for row in rows:
            baseline = row.get("approved_health_baseline")
            health_report = row.get("health_report") or {}
            if not baseline_valid(baseline, dict(row)) or not _health_receipt_fresh(row.get("health_checked_at")) or health_report.get("reasons") or health_report.get("approved_baseline_comparison") not in {"WITHIN_LIMITS", "INSUFFICIENT"}:
                invalidate_profile_cache(str(row["asset"]), state_name="BASELINE_UNVERIFIED")
                continue
            payload = dict(row)
            payload.pop("approved_health_baseline", None)
            payload.pop("health_report", None)
            payload.pop("health_checked_at", None)
            for key in (
                "preferred_families", "penalised_families", "disabled_families",
                "preferred_timeframes", "preferred_sessions", "avoided_sessions",
            ):
                payload[key] = payload.get(key) or []
            payload["health_lease"] = approval_lease(str(payload["profile_id"]))
            lease_seconds = int(payload["health_lease"]["expires_at"] - payload["health_lease"]["issued_at"])
            state.set_sync(f"adaptive:profile:approved:{str(payload['asset']).upper()}",
                           json.dumps(payload, default=str), ex=lease_seconds)
            published += 1
        await session.commit()
    return published


def invalidate_profile_cache(asset: str, *, state_name: str = "SUSPENDED") -> None:
    """Immediately prevent a stale approved profile from remaining active in Redis."""
    state.set_sync(
        f"adaptive:profile:approved:{str(asset).upper()}",
        json.dumps({"asset": str(asset).upper(), "state": str(state_name).upper()}),
        ex=21600,
    )
