"""Persist non-delivered signal decisions for shadow outcome learning.

This module deliberately keeps stale/rejected observations out of live
performance while retaining enough provenance for the shadow tracker and ML
training pipeline to evaluate what would have happened.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Mapping

logger = logging.getLogger(__name__)
_PENDING: set[asyncio.Task] = set()


def _first_target(signal: Mapping[str, Any]) -> Any:
    raw = signal.get("take_profit") or signal.get("take_profits") or signal.get("targets") or signal.get("tp")
    if isinstance(raw, dict):
        raw = list(raw.values())
    if isinstance(raw, (list, tuple)):
        return raw[0] if raw else 0.0
    return raw or 0.0


async def persist_rejected_signal_learning(
    signal: Mapping[str, Any],
    *,
    reason: str,
    rejection_type: str,
    live_price: float | None = None,
    quote: Any | None = None,
    extra_features: Mapping[str, Any] | None = None,
) -> bool:
    """Persist one shadow-only learning row.

    The write uses the existing background-priority rejection store.  Failure
    to obtain background DB capacity never blocks live delivery.
    """
    try:
        from engine.signal_deduplicator import get_deduplicator

        sig = dict(signal or {})
        entry = float(sig.get("entry") or 0.0)
        live = float(live_price or 0.0)
        drift_pct = abs(live - entry) / entry * 100.0 if entry > 0 and live > 0 else None
        features: dict[str, Any] = {
            "learning_category": "SHADOW_REJECTED",
            "rejection_type": str(rejection_type),
            "original_entry": entry,
            "observed_live_price": live or None,
            "drift_pct": drift_pct,
            "score": sig.get("score"),
            "strategy_name": sig.get("strategy_name") or sig.get("strategy"),
            "regime": sig.get("regime"),
            "asset_class": sig.get("asset_class"),
            "generated_at": str(sig.get("created_at") or sig.get("generated_at") or ""),
            "must_not_enter_live_performance": True,
        }
        if quote is not None:
            features.update({
                "quote_provider": getattr(quote, "provider", None),
                "quote_kind": getattr(quote, "quote_kind", None),
                "quote_request_id": getattr(quote, "request_id", None),
                "quote_source_age_ms": getattr(quote, "source_age_ms", None),
                "quote_latency_ms": getattr(quote, "latency_ms", None),
            })
        if extra_features:
            features.update(dict(extra_features))

        await get_deduplicator().persist_rejection(
            asset=str(sig.get("asset") or sig.get("symbol") or "").upper(),
            timeframe=str(sig.get("timeframe") or "1h").lower(),
            direction=str(sig.get("direction") or "long").lower(),
            entry_price=entry,
            stop_loss=float(sig.get("stop_loss") or sig.get("stop") or 0.0),
            take_profit_levels=_first_target(sig),
            ml_probability=float(sig.get("ml_probability") or sig.get("ml_score") or 0.0),
            rejection_reason=str(reason or rejection_type)[:128],
            features=features,
            rejection_type=str(rejection_type),
            signal_id=str(sig.get("signal_id") or sig.get("id") or "") or None,
        )
        logger.info(
            "[rejection_learning] stored asset=%s tf=%s type=%s signal=%s",
            sig.get("asset") or sig.get("symbol"),
            sig.get("timeframe"),
            rejection_type,
            sig.get("signal_id") or sig.get("id"),
        )
        return True
    except Exception as exc:
        logger.warning("[rejection_learning] deferred type=%s err=%s", rejection_type, exc)
        return False


def schedule_rejected_signal_learning(
    signal: Mapping[str, Any],
    *,
    reason: str,
    rejection_type: str,
    live_price: float | None = None,
    quote: Any | None = None,
    extra_features: Mapping[str, Any] | None = None,
) -> asyncio.Task | None:
    """Schedule bounded best-effort persistence on the current event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    task = loop.create_task(
        persist_rejected_signal_learning(
            signal, reason=reason, rejection_type=rejection_type,
            live_price=live_price, quote=quote, extra_features=extra_features,
        ),
        name=f"rejection-learning:{rejection_type}",
    )
    _PENDING.add(task)
    task.add_done_callback(_PENDING.discard)
    return task


__all__ = ["persist_rejected_signal_learning", "schedule_rejected_signal_learning"]
