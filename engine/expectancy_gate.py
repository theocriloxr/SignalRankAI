"""Proof-backed live expectancy and historical performance context.

The engine uses realized signed R multiples from eligible, closed outcomes. It
never invents average win/loss assumptions. A small or unavailable sample is
reported as non-actionable rather than fabricated into a performance claim.
"""

from __future__ import annotations

import logging
import math
import os
import time
from datetime import timedelta
from typing import Any, Dict, Optional

from sqlalchemy import case, exists, func, or_, select

from core.tier_constants import EXPECTANCY_MIN
from db.models import Outcome as SignalOutcome
from db.models import Signal, SignalDelivery
from db.session import get_session
from utils.timeutils import now_utc_naive

logger = logging.getLogger(__name__)

_CONTEXT_CACHE: dict[tuple[str, str, str, int, bool], tuple[float, dict[str, Any]]] = {}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "y"}


def _env_int(name: str, default: int, minimum: int = 0, maximum: int = 100000) -> int:
    try:
        value = int(float(os.getenv(name, str(default)) or default))
    except Exception:
        value = int(default)
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, minimum: float = 0.0, maximum: float = 86400.0) -> float:
    try:
        value = float(os.getenv(name, str(default)) or default)
    except Exception:
        value = float(default)
    return max(minimum, min(maximum, value))


def clear_expectancy_cache() -> None:
    _CONTEXT_CACHE.clear()


def _row_value(row: Any, name: str, index: int, default: Any = None) -> Any:
    if row is None:
        return default
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        try:
            value = mapping.get(name)
            return default if value is None else value
        except Exception:
            pass
    try:
        value = getattr(row, name)
        return default if value is None else value
    except Exception:
        pass
    try:
        value = row[index]
        return default if value is None else value
    except Exception:
        return default


async def get_live_performance_context(
    asset: str,
    strategy: Optional[str] = None,
    timeframe: Optional[str] = None,
    lookback_hours: int = 24 * 30,
) -> dict[str, Any]:
    """Return realized, proof-backed segment performance for decision context."""
    asset_key = str(asset or "").upper().strip()
    strategy_key = str(strategy or "").strip()
    timeframe_key = str(timeframe or "").lower().strip()
    require_delivery = _env_bool("EXPECTANCY_REQUIRE_DELIVERED_PROOF", True)
    lookback = max(1, int(lookback_hours or 24 * 30))
    cache_key = (asset_key, strategy_key.lower(), timeframe_key, lookback, require_delivery)
    cache_ttl = _env_float("EXPECTANCY_CACHE_SECONDS", 120.0, minimum=0.0, maximum=3600.0)
    now_mono = time.monotonic()
    cached = _CONTEXT_CACHE.get(cache_key)
    if cached and cache_ttl > 0 and now_mono - cached[0] <= cache_ttl:
        result = dict(cached[1])
        result["cache_hit"] = True
        return result

    min_samples = _env_int("EXPECTANCY_MIN_SAMPLE", 10, minimum=1, maximum=10000)
    context: dict[str, Any] = {
        "actionable": False,
        "asset": asset_key,
        "strategy": strategy_key or None,
        "timeframe": timeframe_key or None,
        "lookback_hours": lookback,
        "sample_size": 0,
        "wins": 0,
        "losses": 0,
        "breakeven": 0,
        "win_rate": None,
        "win_rate_lower_95": None,
        "win_rate_upper_95": None,
        "decisive_samples": 0,
        "avg_r": None,
        "expectancy_r": None,
        "avg_win_r": None,
        "avg_loss_r": None,
        "profit_factor": None,
        "delivery_proof_required": require_delivery,
        "minimum_sample": min_samples,
        "reason": "not_loaded",
        "cache_hit": False,
    }
    if not asset_key:
        context["reason"] = "asset_missing"
        return context

    cutoff = now_utc_naive() - timedelta(hours=lookback)
    positive_r = case((SignalOutcome.r_multiple > 0, SignalOutcome.r_multiple), else_=None)
    negative_r = case((SignalOutcome.r_multiple < 0, SignalOutcome.r_multiple), else_=None)
    wins = case((SignalOutcome.r_multiple > 0, 1), else_=0)
    losses = case((SignalOutcome.r_multiple < 0, 1), else_=0)
    query = (
        select(
            func.count(SignalOutcome.id).label("sample_size"),
            func.sum(wins).label("wins"),
            func.sum(losses).label("losses"),
            func.avg(SignalOutcome.r_multiple).label("avg_r"),
            func.avg(positive_r).label("avg_win_r"),
            func.avg(negative_r).label("avg_loss_r"),
            func.sum(positive_r).label("gross_win_r"),
            func.sum(negative_r).label("gross_loss_r"),
        )
        .select_from(SignalOutcome)
        .join(Signal, SignalOutcome.signal_id == Signal.signal_id)
        .where(
            SignalOutcome.closed_at.is_not(None),
            SignalOutcome.closed_at >= cutoff,
            SignalOutcome.r_multiple.is_not(None),
            Signal.asset == asset_key,
            or_(
                SignalOutcome.performance_inclusion_status.is_(None),
                SignalOutcome.performance_inclusion_status.in_(("eligible", "included")),
            ),
        )
    )
    if strategy_key:
        query = query.where(Signal.strategy_name == strategy_key)
    if timeframe_key:
        query = query.where(func.lower(Signal.timeframe) == timeframe_key)
    if require_delivery:
        query = query.where(
            exists().where(
                SignalDelivery.signal_id == Signal.signal_id,
                SignalDelivery.sent_ok.is_(True),
            )
        )

    try:
        async with get_session(priority="background", label="live_expectancy_context") as session:
            row = (await session.execute(query)).first()
            await session.rollback()
    except Exception as exc:
        context["reason"] = f"query_failed:{type(exc).__name__}"
        logger.warning(
            "[expectancy] context query failed asset=%s strategy=%s tf=%s error=%s",
            asset_key,
            strategy_key or "*",
            timeframe_key or "*",
            type(exc).__name__,
        )
        return context

    sample_size = int(_row_value(row, "sample_size", 0, 0) or 0)
    win_count = int(_row_value(row, "wins", 1, 0) or 0)
    loss_count = int(_row_value(row, "losses", 2, 0) or 0)
    avg_r = _row_value(row, "avg_r", 3)
    avg_win_r = _row_value(row, "avg_win_r", 4)
    avg_loss_r = _row_value(row, "avg_loss_r", 5)
    gross_win = _row_value(row, "gross_win_r", 6, 0.0)
    gross_loss = _row_value(row, "gross_loss_r", 7, 0.0)

    decisive = win_count + loss_count
    win_rate = (win_count / decisive) if decisive > 0 else None
    wilson_lower = None
    wilson_upper = None
    if decisive > 0 and win_rate is not None:
        # Wilson 95% interval is stable for small samples and gives downstream
        # ranking/AI reviewers an uncertainty-aware view of historical edge.
        z = 1.959963984540054
        n = float(decisive)
        denominator = 1.0 + (z * z / n)
        center = win_rate + (z * z / (2.0 * n))
        margin = z * math.sqrt((win_rate * (1.0 - win_rate) / n) + (z * z / (4.0 * n * n)))
        wilson_lower = max(0.0, (center - margin) / denominator)
        wilson_upper = min(1.0, (center + margin) / denominator)
    try:
        avg_r_f = float(avg_r) if avg_r is not None else None
    except (TypeError, ValueError):
        avg_r_f = None
    try:
        avg_win_f = float(avg_win_r) if avg_win_r is not None else None
    except (TypeError, ValueError):
        avg_win_f = None
    try:
        avg_loss_f = abs(float(avg_loss_r)) if avg_loss_r is not None else None
    except (TypeError, ValueError):
        avg_loss_f = None
    try:
        gross_win_f = max(0.0, float(gross_win or 0.0))
        gross_loss_f = abs(min(0.0, float(gross_loss or 0.0)))
    except (TypeError, ValueError):
        gross_win_f, gross_loss_f = 0.0, 0.0
    profit_factor = gross_win_f / gross_loss_f if gross_loss_f > 0 else None

    context.update(
        {
            "sample_size": sample_size,
            "wins": win_count,
            "losses": loss_count,
            "breakeven": max(0, sample_size - decisive),
            "win_rate": round(win_rate, 6) if win_rate is not None else None,
            "win_rate_lower_95": round(wilson_lower, 6) if wilson_lower is not None else None,
            "win_rate_upper_95": round(wilson_upper, 6) if wilson_upper is not None else None,
            "decisive_samples": decisive,
            "avg_r": round(avg_r_f, 6) if avg_r_f is not None else None,
            "expectancy_r": round(avg_r_f, 6) if avg_r_f is not None else None,
            "avg_win_r": round(avg_win_f, 6) if avg_win_f is not None else None,
            "avg_loss_r": round(avg_loss_f, 6) if avg_loss_f is not None else None,
            "profit_factor": round(profit_factor, 6) if profit_factor is not None else None,
            "actionable": bool(sample_size >= min_samples and avg_r_f is not None),
            "reason": "ok" if sample_size >= min_samples and avg_r_f is not None else "insufficient_sample",
        }
    )
    if cache_ttl > 0:
        _CONTEXT_CACHE[cache_key] = (now_mono, dict(context))
    logger.debug(
        "[expectancy] asset=%s strategy=%s tf=%s n=%s wr=%s avg_r=%s pf=%s actionable=%s",
        asset_key,
        strategy_key or "*",
        timeframe_key or "*",
        sample_size,
        context.get("win_rate"),
        context.get("avg_r"),
        context.get("profit_factor"),
        context.get("actionable"),
    )
    return context


async def get_best_live_performance_context(
    asset: str,
    *,
    strategy: Optional[str] = None,
    timeframe: Optional[str] = None,
    lookback_hours: int = 24 * 30,
) -> dict[str, Any]:
    """Prefer the most specific proof-backed segment with enough observations.

    This avoids treating all history for an asset as equally relevant while
    also refusing to overfit tiny strategy/timeframe samples. Every level uses
    the same realized-R, delivery-proof and minimum-sample rules.
    """
    asset_key = str(asset or "").upper().strip()
    strategy_key = str(strategy or "").strip()
    timeframe_key = str(timeframe or "").lower().strip()
    levels: list[tuple[str, Optional[str], Optional[str]]] = []
    if strategy_key and timeframe_key:
        levels.append(("asset_strategy_timeframe", strategy_key, timeframe_key))
    if strategy_key:
        levels.append(("asset_strategy", strategy_key, None))
    if timeframe_key:
        levels.append(("asset_timeframe", None, timeframe_key))
    levels.append(("asset", None, None))

    seen: set[tuple[str, str]] = set()
    candidates: list[dict[str, Any]] = []
    for scope, scope_strategy, scope_timeframe in levels:
        key = (str(scope_strategy or "").lower(), str(scope_timeframe or "").lower())
        if key in seen:
            continue
        seen.add(key)
        context = await get_live_performance_context(
            asset_key,
            strategy=scope_strategy,
            timeframe=scope_timeframe,
            lookback_hours=lookback_hours,
        )
        context = dict(context)
        context["scope"] = scope
        candidates.append(context)
        if bool(context.get("actionable")):
            context["fallback_depth"] = len(candidates) - 1
            return context

    if candidates:
        best_index = max(
            range(len(candidates)),
            key=lambda idx: int(candidates[idx].get("sample_size") or 0),
        )
        best = dict(candidates[best_index])
        best["actionable"] = False
        best["fallback_depth"] = best_index
        best["reason"] = str(best.get("reason") or "insufficient_sample")
        return best
    return {
        "actionable": False,
        "asset": asset_key,
        "strategy": strategy_key or None,
        "timeframe": timeframe_key or None,
        "scope": "none",
        "sample_size": 0,
        "reason": "no_evidence",
        "fallback_depth": 0,
    }


async def get_live_expectancy(
    asset: str,
    strategy: Optional[str] = None,
    lookback_hours: int = 168,
) -> float:
    """Compatibility API returning realized expectancy R when evidence is sufficient."""
    context = await get_live_performance_context(
        asset,
        strategy=strategy,
        lookback_hours=lookback_hours,
    )
    if context.get("actionable") and context.get("expectancy_r") is not None:
        return float(context["expectancy_r"])
    logger.info(
        "[expectancy] insufficient evidence asset=%s strategy=%s n=%s default=%s",
        asset,
        strategy or "*",
        context.get("sample_size", 0),
        EXPECTANCY_MIN,
    )
    return float(EXPECTANCY_MIN)


async def expectancy_gate(signal: Dict[str, Any]) -> bool:
    """Gate function: block only when actionable realized expectancy is below the floor."""
    asset = str(signal.get("asset") or "")
    strategy = signal.get("strategy_name") or signal.get("strategy")
    timeframe = signal.get("timeframe")
    if not asset:
        logger.warning("No asset in signal, passing expectancy gate")
        return True

    if signal.get("live_expectancy") is not None:
        exp = float(signal.get("live_expectancy"))
        actionable = bool(signal.get("historical_evidence_actionable", True))
    else:
        context = await get_live_performance_context(
            asset,
            strategy=strategy,
            timeframe=timeframe,
        )
        actionable = bool(context.get("actionable"))
        if actionable and context.get("expectancy_r") is not None:
            exp = float(context["expectancy_r"])
            signal["live_expectancy"] = exp
        else:
            signal["historical_evidence_actionable"] = False
            return True

    gate_pass = (not actionable) or exp >= EXPECTANCY_MIN
    if not gate_pass:
        logger.info(
            "Expectancy BLOCK: %s/%s exp=%.3f < %.3f",
            asset,
            strategy or "*",
            exp,
            EXPECTANCY_MIN,
        )
    return bool(gate_pass)


async def global_expectancy_check(global_dd: float) -> bool:
    from core.tier_constants import DD_HARD_LIMIT

    return global_dd < DD_HARD_LIMIT


async def validate_expectancy_pipeline(signal: Dict[str, Any]) -> Dict[str, Any]:
    signal["expectancy_pass"] = await expectancy_gate(signal)
    return signal


__all__ = [
    "clear_expectancy_cache",
    "get_live_performance_context",
    "get_best_live_performance_context",
    "get_live_expectancy",
    "expectancy_gate",
    "global_expectancy_check",
    "validate_expectancy_pipeline",
]
