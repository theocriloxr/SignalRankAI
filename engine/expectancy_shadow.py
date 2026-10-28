"""Shadow evidence for the expectancy gate (owner decision, 28 Oct 2026).

Production runs with ``EXPECTANCY_HARD_BLOCK_ENABLED``: a candidate needs a
qualified expectancy from at least ``EXPECTANCY_MIN_SAMPLE`` proof-backed
delivered outcomes in 30 days. With no deliveries, every candidate is refused
and no new evidence can ever form, so the gate locks itself shut.

This module keeps the gate and gives it a second, stricter source of evidence:

1. A candidate refused only for ``expectancy_unavailable`` is recorded once (a
   setup seen on many cycles counts once) as a ``decision_log`` row with
   ``layer='expectancy'``.
2. The shadow outcome worker follows those rows to their stop or final target
   on later market data and stores the realized R (target: planned R; stop or
   an ambiguous bar: -1 R).
3. With ``EXPECTANCY_SHADOW_BOOTSTRAP_ENABLED`` set, the gate may use that
   evidence only when the sample is at least ``EXPECTANCY_SHADOW_SAMPLE_MULTIPLIER``
   (default 2) times the live minimum and the lower 95% bound of expectancy,
   after a per-trade cost haircut, is itself at or above ``EXPECTANCY_MIN``. The
   gate then sees that conservative bound, never the mean.

Recording is on by default (observation only); admission is off by default.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
from datetime import timedelta
from typing import Any, Mapping, Sequence

from core.tier_constants import EXPECTANCY_MIN

logger = logging.getLogger(__name__)

LAYER = "expectancy"
REASON = "risk/expectancy_unavailable"


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _number(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name) or default)
    except ValueError:
        return default
    return min(maximum, max(minimum, value)) if math.isfinite(value) else default


def recording_enabled() -> bool:
    return _flag("EXPECTANCY_SHADOW_RECORDING_ENABLED", True)


def bootstrap_enabled() -> bool:
    return _flag("EXPECTANCY_SHADOW_BOOTSTRAP_ENABLED", False)


def _sig(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{number:.5g}" if math.isfinite(number) else ""


def shadow_key(signal: Mapping[str, Any]) -> str | None:
    """Identity of one trade setup: the same levels on later cycles are the same shadow trade."""
    parts = [str(signal.get("asset") or "").upper(), str(signal.get("strategy_name") or "").lower(),
             str(signal.get("timeframe") or "").lower(), str(signal.get("direction") or "").upper(),
             _sig(signal.get("entry")), _sig(signal.get("stop_loss") or signal.get("stop"))]
    if not all(parts[i] for i in (0, 3, 4, 5)):
        return None
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


def claim(signal: Mapping[str, Any], state: Any) -> str | None:
    """Return the setup key the first time it is seen within the de-duplication window."""
    key = shadow_key(signal)
    if key is None:
        return None
    ttl = int(_number("EXPECTANCY_SHADOW_DEDUP_SECONDS", 86400, 3600, 30 * 86400))
    redis_key = f"expectancy_shadow:seen:{key}"
    try:
        if state.get_sync(redis_key):
            return None
        state.set_sync(redis_key, "1", ex=ttl)
    except Exception:
        logger.debug("[expectancy_shadow] de-duplication store unavailable", exc_info=True)
        return None  # without de-duplication, recording would inflate the sample
    return key


def _final_target(take_profit: Any) -> float | None:
    if isinstance(take_profit, (list, tuple)):
        values = [t for t in take_profit if t is not None]
        take_profit = values[-1] if values else None
    if isinstance(take_profit, str):
        cleaned = take_profit.strip().strip("[]").split(",")
        take_profit = cleaned[-1] if cleaned and cleaned[-1].strip() else None
    try:
        value = float(take_profit)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def realized_r(direction: Any, entry: Any, stop: Any, take_profit: Any, outcome: str) -> float | None:
    """Realized R of a tracked shadow trade; ambiguous bars count as losses."""
    try:
        entry_f, stop_f = float(entry), float(stop)
    except (TypeError, ValueError):
        return None
    risk = abs(entry_f - stop_f)
    if not (math.isfinite(risk) and risk > 0):
        return None
    outcome = str(outcome or "").lower()
    if outcome in {"sl", "ambiguous"}:
        return -1.0
    if outcome.startswith("tp"):
        target = _final_target(take_profit)
        if target is None:
            return None
        reward = (target - entry_f) if str(direction).lower() in {"long", "buy"} else (entry_f - target)
        return reward / risk if reward > 0 else None
    return None


def summarize(r_values: Sequence[float]) -> dict[str, Any]:
    """Stricter-than-live qualification of shadow evidence."""
    live_minimum = int(_number("EXPECTANCY_MIN_SAMPLE", 10, 1, 10000))
    multiplier = _number("EXPECTANCY_SHADOW_SAMPLE_MULTIPLIER", 2.0, 1.0, 20.0)
    required = int(math.ceil(live_minimum * multiplier))
    haircut = _number("EXPECTANCY_SHADOW_COST_R", 0.05, 0.0, 1.0)
    values = [float(v) for v in r_values if v is not None and math.isfinite(float(v))]
    n = len(values)
    result: dict[str, Any] = {"sample_size": n, "required_sample": required, "cost_haircut_r": haircut,
                              "minimum_expectancy_r": float(EXPECTANCY_MIN), "actionable": False}
    if n < 2:
        result["reason"] = "insufficient_sample"
        return result
    mean = sum(values) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))
    lower = mean - 1.96 * sd / math.sqrt(n) - haircut
    result.update(mean_r=round(mean, 4), expectancy_lower_95_r=round(lower, 4),
                  wins=sum(1 for v in values if v > 0), losses=sum(1 for v in values if v <= 0))
    if n < required:
        result["reason"] = "insufficient_sample"
    elif lower < float(EXPECTANCY_MIN):
        result["reason"] = "lower_bound_below_minimum"
    else:
        result["actionable"] = True
        result["reason"] = "ok"
    return result


async def get_shadow_performance_context(asset: str, *, strategy: str | None = None,
                                         lookback_hours: int = 24 * 30) -> dict[str, Any]:
    """Shadow evidence for an asset (strategy first, then all strategies), never more lenient than live."""
    from sqlalchemy import select

    from db.models import DecisionLog
    from db.session import get_session
    from utils.timeutils import now_utc_naive

    asset_key = str(asset or "").upper().strip()
    cutoff = now_utc_naive() - timedelta(hours=max(24, int(lookback_hours)))
    async with get_session(priority="background", label="expectancy_shadow_context", timeout_seconds=4.0) as session:
        rows = (await session.execute(
            select(DecisionLog.meta)
            .where(DecisionLog.decision == "rejected")
            .where(DecisionLog.meta["layer"].as_string() == LAYER)
            .where(DecisionLog.asset == asset_key)
            .where(DecisionLog.created_at >= cutoff)
        )).scalars().all()
        await session.rollback()
    tracked = [dict(meta or {}) for meta in rows if (meta or {}).get("shadow_r") is not None]
    scopes = []
    if strategy:
        scopes.append(("asset_strategy", [m["shadow_r"] for m in tracked
                                          if str(m.get("strategy_name") or "").lower() == strategy.lower()]))
    scopes.append(("asset", [m["shadow_r"] for m in tracked]))
    best: dict[str, Any] | None = None
    for scope, values in scopes:
        summary = {**summarize(values), "scope": scope, "asset": asset_key, "source": "shadow"}
        if summary["actionable"]:
            return summary
        best = best or summary
    return best or {"actionable": False, "sample_size": 0, "scope": "none", "asset": asset_key, "source": "shadow"}


__all__ = ["LAYER", "REASON", "bootstrap_enabled", "claim", "get_shadow_performance_context",
           "realized_r", "recording_enabled", "shadow_key", "summarize"]
