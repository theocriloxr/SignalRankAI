"""Per-asset strategy scorecard learned from every tracked outcome (2 Nov 2026).

Each strategy is scored separately for each asset, timeframe and direction, so
the engine learns, for example, that ``EMA Trend`` works on ``BTCUSDT 4h`` but
loses on ``XRPUSDT 5m``. Evidence comes from two sources:

- ``issued``: delivered signals with an eligible closed outcome (``outcomes``);
- ``shadow``: every rejected candidate that ``engine/shadow_outcome_worker.py``
  followed forward to its stop or target (``decision_log`` rows with
  ``outcome_tracked_at``). These are tens of thousands of setups a day, so a
  strategy can be judged on an asset long before it has delivered signals there.

The analytics role rebuilds the scorecard on a schedule and publishes it to
Redis. The engine reads it (``scorecard_adjustment``) and, depending on
``STRATEGY_SCORECARD_MODE``:

- ``off``: does nothing;
- ``shadow`` (default): annotates each candidate with what the scorecard would
  do, without changing the score;
- ``apply``: multiplies the score by a bounded factor (default 0.85-1.15).

A cell influences a score only when its Wilson 95% interval for the win rate
lies clearly above or below the break-even win rate implied by the cell's own
average win size. Thin or undecided cells always resolve to 1.0, so no
strategy is promoted or suppressed without evidence. Nothing here can create a
signal or bypass a risk, ML or validation gate.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from collections import defaultdict
from functools import lru_cache
from datetime import timedelta
from typing import Any, Iterable, Mapping

logger = logging.getLogger(__name__)

REDIS_KEY = "strategy_scorecard:v1"
_SCOPES = ("asset_tf_dir", "asset_tf", "asset", "class_tf", "class")


def _env_float(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float((os.getenv(name) or str(default)).strip())
    except ValueError:
        value = default
    if not math.isfinite(value):
        value = default
    return max(low, min(high, value))


def _env_int(name: str, default: int, low: int, high: int) -> int:
    return int(_env_float(name, float(default), float(low), float(high)))


def scorecard_mode() -> str:
    mode = (os.getenv("STRATEGY_SCORECARD_MODE") or "shadow").strip().lower()
    return mode if mode in {"off", "shadow", "apply"} else "shadow"


def wilson_interval(wins: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 1.0
    p = max(0.0, min(1.0, wins / total))
    denom = 1.0 + z * z / total
    centre = p + z * z / (2.0 * total)
    margin = z * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total))
    return max(0.0, (centre - margin) / denom), min(1.0, (centre + margin) / denom)


def _targets(take_profit: Any) -> list[float]:
    raw: Iterable[Any]
    if isinstance(take_profit, (list, tuple)):
        raw = take_profit
    elif isinstance(take_profit, str):
        raw = take_profit.strip().strip("[]").split(",")
    else:
        raw = [take_profit]
    out: list[float] = []
    for item in raw:
        try:
            value = float(str(item).strip()) if isinstance(item, str) else float(item)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0:
            out.append(value)
    return out


def outcome_r(direction: Any, entry: Any, stop: Any, take_profit: Any, outcome: Any) -> float | None:
    """R of a tracked trade, using the target level that was actually reached.

    ``tp1`` is valued at the first target and ``tp3`` at the third, so an early
    target is not credited with the final target's reward. Ambiguous bars (stop
    and target in the same candle) count as losses.
    """
    try:
        entry_f, stop_f = float(entry), float(stop)
    except (TypeError, ValueError):
        return None
    risk = abs(entry_f - stop_f)
    if not (math.isfinite(risk) and risk > 0):
        return None
    label = str(outcome or "").strip().lower()
    if label in {"sl", "ambiguous", "loss"}:
        return -1.0
    if not label.startswith("tp"):
        return None
    targets = _targets(take_profit)
    if not targets:
        return None
    try:
        level = max(1, int(label[2:] or 1))
    except ValueError:
        level = len(targets)
    target = targets[min(level, len(targets)) - 1]
    is_long = str(direction or "").strip().lower() in {"long", "buy"}
    reward = (target - entry_f) if is_long else (entry_f - target)
    if reward <= 0:
        return None
    return min(reward / risk, _env_float("STRATEGY_SCORECARD_MAX_WIN_R", 10.0, 1.0, 50.0))


def _norm(value: Any, default: str = "unknown") -> str:
    text = str(value or "").strip()
    return text if text else default


def _asset_class(asset: str, explicit: Any = None) -> str:
    if explicit:
        return str(explicit).strip().lower()
    return _classify(asset)


@lru_cache(maxsize=4096)
def _classify(asset: str) -> str:
    try:
        from services.asset_mapper import classify_asset

        value = classify_asset(asset)
        if value:
            return str(value).strip().lower()
    except Exception:
        pass
    upper = asset.upper()
    return "crypto" if upper.endswith(("USDT", "USDC", "PERP")) else "other"


_TIMEFRAME_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "2h": 7200,
    "4h": 14400, "6h": 21600, "8h": 28800, "12h": 43200, "1d": 86400, "24h": 86400, "1w": 604800,
}


def bar_index(created_at: Any, timeframe: Any) -> int | None:
    """Index of the timeframe bar a decision was logged in (UTC-naive timestamps)."""
    if created_at is None or not hasattr(created_at, "timestamp"):
        return None
    seconds = _TIMEFRAME_SECONDS.get(str(timeframe or "").strip().lower(), 3600)
    try:
        if getattr(created_at, "tzinfo", None) is None:
            from datetime import timezone

            created_at = created_at.replace(tzinfo=timezone.utc)
        return int(created_at.timestamp() // seconds)
    except (OverflowError, OSError, ValueError):
        return None


def cell_keys(asset: str, timeframe: str, strategy: str, direction: str, asset_class: str) -> list[tuple[str, str]]:
    """Scope keys from the most specific to the most general."""
    a, tf, st = asset.upper(), timeframe.lower(), strategy.lower()
    d = "long" if direction.lower() in {"long", "buy"} else "short"
    return [
        ("asset_tf_dir", f"{a}|{tf}|{st}|{d}"),
        ("asset_tf", f"{a}|{tf}|{st}"),
        ("asset", f"{a}|{st}"),
        ("class_tf", f"{asset_class}|{tf}|{st}"),
        ("class", f"{asset_class}|{st}"),
    ]


class _Cell:
    __slots__ = ("wins", "losses", "sum_r", "sum_win_r", "issued", "shadow")

    def __init__(self) -> None:
        self.wins = 0
        self.losses = 0
        self.sum_r = 0.0
        self.sum_win_r = 0.0
        self.issued = 0
        self.shadow = 0

    def add(self, r: float, source: str, weight: int = 1) -> None:
        for _ in range(max(1, weight)):
            if r > 0:
                self.wins += 1
                self.sum_win_r += r
            else:
                self.losses += 1
            self.sum_r += r
        if source == "issued":
            self.issued += 1
        else:
            self.shadow += 1


def summarise_cell(cell: _Cell) -> dict[str, Any]:
    n = cell.wins + cell.losses
    lower, upper = wilson_interval(cell.wins, n)
    avg_win_r = cell.sum_win_r / cell.wins if cell.wins else 0.0
    # Win rate needed to break even when losses cost 1R and wins pay avg_win_r.
    breakeven = 1.0 / (1.0 + avg_win_r) if avg_win_r > 0 else 1.0
    return {
        "n": n,
        "wins": cell.wins,
        "win_rate": round(cell.wins / n, 4) if n else None,
        "win_lower_95": round(lower, 4),
        "win_upper_95": round(upper, 4),
        "avg_r": round(cell.sum_r / n, 4) if n else None,
        "avg_win_r": round(avg_win_r, 4),
        "breakeven_win_rate": round(breakeven, 4),
        "issued": cell.issued,
        "shadow": cell.shadow,
    }


def build_scorecard(rows: Iterable[Mapping[str, Any]], *, issued_weight: int | None = None) -> dict[str, Any]:
    """Aggregate tracked rows into scope cells.

    Each row needs ``asset``, ``timeframe``, ``strategy``, ``direction``,
    ``r`` and ``source`` (``issued`` or ``shadow``). Issued outcomes count
    ``STRATEGY_SCORECARD_ISSUED_WEIGHT`` times (default 3), because they went
    through every gate and were delivered at a real price.
    """
    weight = issued_weight if issued_weight is not None else _env_int("STRATEGY_SCORECARD_ISSUED_WEIGHT", 3, 1, 20)
    cells: dict[str, dict[str, _Cell]] = {scope: defaultdict(_Cell) for scope in _SCOPES}
    used = 0
    duplicates = 0
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        r = row.get("r")
        if r is None:
            continue
        try:
            r = float(r)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(r):
            continue
        asset = _norm(row.get("asset")).upper()
        strategy = _norm(row.get("strategy"))
        if strategy == "unknown" or asset == "UNKNOWN":
            continue
        source = "issued" if row.get("source") == "issued" else "shadow"
        bar = row.get("bar")
        if source == "shadow" and bar is not None:
            # The engine re-evaluates the same setup on every scan, so one
            # bar can log the same rejected candidate hundreds of times (2 Nov:
            # 3,470 XAGUSD 4h EMA Trend rows in about a day). One bar of one
            # strategy and direction is one trade opportunity.
            dedup = (asset, _norm(row.get("timeframe")).lower(), strategy.lower(),
                     _norm(row.get("direction"), "long").lower() in {"long", "buy"}, bar)
            if dedup in seen:
                duplicates += 1
                continue
            seen.add(dedup)
        keys = cell_keys(
            asset,
            _norm(row.get("timeframe")),
            strategy,
            _norm(row.get("direction"), "long"),
            _asset_class(asset, row.get("asset_class")),
        )
        for scope, key in keys:
            cells[scope][key].add(r, source, weight if source == "issued" else 1)
        used += 1
    min_n = _env_int("STRATEGY_SCORECARD_MIN_PUBLISH_SAMPLES", 10, 1, 10000)
    published = {
        scope: {key: summarise_cell(cell) for key, cell in scoped.items() if cell.wins + cell.losses >= min_n}
        for scope, scoped in cells.items()
    }
    return {"rows_used": used, "duplicates_skipped": duplicates, "cells": published}


def adjustment_for_cell(cell: Mapping[str, Any] | None) -> tuple[float, str]:
    """Bounded multiplier for one cell, 1.0 unless the evidence is decisive."""
    if not cell:
        return 1.0, "no_evidence"
    min_n = _env_int("STRATEGY_SCORECARD_MIN_SAMPLES", 40, 10, 100000)
    n = int(cell.get("n") or 0)
    if n < min_n:
        return 1.0, f"insufficient_samples:{n}<{min_n}"
    max_up = _env_float("STRATEGY_SCORECARD_MAX_BOOST", 1.15, 1.0, 1.25)
    max_down = _env_float("STRATEGY_SCORECARD_MAX_PENALTY", 0.85, 0.70, 1.0)
    margin = _env_float("STRATEGY_SCORECARD_EDGE_MARGIN", 0.02, 0.0, 0.2)
    lower = float(cell.get("win_lower_95") or 0.0)
    upper = float(cell.get("win_upper_95") or 1.0)
    breakeven = float(cell.get("breakeven_win_rate") or 1.0)
    avg_r = float(cell.get("avg_r") or 0.0)
    if lower > breakeven + margin and avg_r > 0:
        edge = min(1.0, (lower - breakeven) / 0.15)
        return round(1.0 + (max_up - 1.0) * edge, 4), "supported_edge"
    if upper < breakeven - margin and avg_r < 0:
        edge = min(1.0, (breakeven - upper) / 0.15)
        return round(1.0 - (1.0 - max_down) * edge, 4), "supported_negative_edge"
    return 1.0, "undecided"


def lookup(scorecard: Mapping[str, Any] | None, *, asset: str, timeframe: str, strategy: str,
           direction: str, asset_class: str | None = None) -> dict[str, Any]:
    """Most specific cell with enough samples, then its multiplier."""
    cells = dict((scorecard or {}).get("cells") or {})
    min_n = _env_int("STRATEGY_SCORECARD_MIN_SAMPLES", 40, 10, 100000)
    klass = asset_class or _asset_class(asset)
    chosen_scope, chosen_key, chosen = None, None, None
    for scope, key in cell_keys(asset, timeframe, strategy, direction, klass):
        cell = (cells.get(scope) or {}).get(key)
        if cell and int(cell.get("n") or 0) >= min_n:
            chosen_scope, chosen_key, chosen = scope, key, cell
            break
    multiplier, reason = adjustment_for_cell(chosen)
    return {"scope": chosen_scope, "key": chosen_key, "cell": chosen, "multiplier": multiplier, "reason": reason}


# --------------------------------------------------------------------------- engine side

_cache: dict[str, Any] = {"loaded_at": 0.0, "scorecard": None}


def _load_cached() -> dict[str, Any] | None:
    ttl = _env_float("STRATEGY_SCORECARD_CACHE_SECONDS", 300.0, 10.0, 86400.0)
    if _cache["scorecard"] is not None and time.monotonic() - float(_cache["loaded_at"]) < ttl:
        return _cache["scorecard"]
    try:
        from core.redis_state import state

        raw = state.get_sync(REDIS_KEY)
        payload = json.loads(raw) if raw else None
    except Exception:
        logger.debug("[strategy_scorecard] cache load failed", exc_info=True)
        payload = None
    _cache.update(loaded_at=time.monotonic(), scorecard=payload)
    return payload


def scorecard_adjustment(sig: Mapping[str, Any], asset: str | None = None) -> dict[str, Any]:
    """Engine hook: what the scorecard says about one candidate."""
    mode = scorecard_mode()
    if mode == "off":
        return {"mode": mode, "multiplier": 1.0, "applied": False}
    result = lookup(
        _load_cached(),
        asset=str(sig.get("asset") or asset or ""),
        timeframe=str(sig.get("timeframe") or ""),
        strategy=str(sig.get("strategy_name") or sig.get("strategy") or ""),
        direction=str(sig.get("direction") or ""),
        asset_class=str(sig.get("asset_class") or "") or None,
    )
    result["mode"] = mode
    result["applied"] = bool(mode == "apply" and result["multiplier"] != 1.0)
    return result


# --------------------------------------------------------------------------- analytics side

async def _first_id_after(session: Any, cutoff: Any, max_id: int) -> int:
    """Binary search over the primary key; ``decision_log.created_at`` has no index."""
    from sqlalchemy import text

    low, high = 0, max_id
    while low < high:
        mid = (low + high) // 2
        row = (
            await session.execute(
                text("SELECT id, created_at FROM decision_log WHERE id >= :mid ORDER BY id LIMIT 1"), {"mid": mid}
            )
        ).first()
        if row is None or row[1] >= cutoff:
            high = mid
        else:
            low = int(row[0]) + 1
    return low


async def _load_rows(lookback_days: int) -> list[dict[str, Any]]:
    from sqlalchemy import text

    from db.session import get_session
    from utils.timeutils import now_utc_naive

    cutoff = now_utc_naive() - timedelta(days=lookback_days)
    page = _env_int("STRATEGY_SCORECARD_PAGE_ROWS", 5000, 500, 50000)
    max_pages = _env_int("STRATEGY_SCORECARD_MAX_PAGES", 400, 1, 10000)
    timeout = _env_float("STRATEGY_SCORECARD_DB_TIMEOUT_SECONDS", 60.0, 5.0, 900.0)
    rows: list[dict[str, Any]] = []

    async with get_session(priority="analytics", label="strategy_scorecard.issued", timeout_seconds=timeout,
                           drop_if_busy=False) as session:
        issued = (
            await session.execute(
                text(
                    """
                    SELECT s.asset, s.asset_class, s.timeframe, s.strategy_name, s.direction, o.r_multiple
                    FROM signals s JOIN outcomes o ON o.signal_id = s.signal_id
                    WHERE s.created_at >= :cutoff AND o.r_multiple IS NOT NULL AND o.closed_at IS NOT NULL
                      AND o.performance_inclusion_status = 'eligible'
                    """
                ),
                {"cutoff": cutoff},
            )
        ).all()
        for asset, asset_class, tf, strategy, direction, r in issued:
            rows.append({"asset": asset, "asset_class": asset_class, "timeframe": tf, "strategy": strategy,
                         "direction": direction, "r": r, "source": "issued"})
        max_id = int((await session.execute(text("SELECT COALESCE(MAX(id), 0) FROM decision_log"))).scalar() or 0)
        start_id = await _first_id_after(session, cutoff, max_id)

    after = start_id - 1
    for _ in range(max_pages):
        async with get_session(priority="analytics", label="strategy_scorecard.shadow", timeout_seconds=timeout,
                               drop_if_busy=False) as session:
            batch = (
                await session.execute(
                    text(
                        """
                        SELECT id, asset, timeframe, created_at,
                               meta::jsonb->>'direction', meta::jsonb->>'entry', meta::jsonb->>'stop_loss',
                               meta::jsonb->'take_profit', meta::jsonb->>'actual_outcome',
                               COALESCE(meta::jsonb->'features'->>'strategy_name',
                                        meta::jsonb->'features'->>'strategy')
                        FROM decision_log
                        WHERE id > :after AND id <= :after + :page
                          AND meta::jsonb->>'outcome_tracked_at' IS NOT NULL
                        """
                    ),
                    {"after": after, "page": page},
                )
            ).all()
        for _id, asset, tf, created_at, direction, entry, stop, tp, outcome, strategy in batch:
            r = outcome_r(direction, entry, stop, tp, outcome)
            if r is not None:
                rows.append({"asset": asset, "timeframe": tf, "strategy": strategy, "direction": direction,
                             "r": r, "source": "shadow", "bar": bar_index(created_at, tf)})
        after += page
        if after >= max_id:
            break
        await asyncio.sleep(0)
    return rows


async def rebuild_once() -> dict[str, Any]:
    lookback = _env_int("STRATEGY_SCORECARD_LOOKBACK_DAYS", 30, 1, 365)
    started = time.monotonic()
    rows = await _load_rows(lookback)
    scorecard = build_scorecard(rows)
    scorecard.update(
        built_at=time.time(),
        lookback_days=lookback,
        build_seconds=round(time.monotonic() - started, 1),
        sources={"issued": sum(1 for r in rows if r["source"] == "issued"),
                 "shadow": sum(1 for r in rows if r["source"] == "shadow")},
    )
    from core.redis_state import state

    ttl = _env_int("STRATEGY_SCORECARD_TTL_SECONDS", 3 * 86400, 3600, 30 * 86400)
    state.set_sync(REDIS_KEY, json.dumps(scorecard, separators=(",", ":")), ttl)
    cells = scorecard["cells"]
    decisive = [
        (key, adjustment_for_cell(cell))
        for key, cell in (cells.get("asset_tf") or {}).items()
    ]
    boosted = sum(1 for _, (m, _) in decisive if m > 1.0)
    penalised = sum(1 for _, (m, _) in decisive if m < 1.0)
    summary = {
        "rows_used": scorecard["rows_used"],
        "duplicates_skipped": scorecard.get("duplicates_skipped", 0),
        "sources": scorecard["sources"],
        "cells": {scope: len(v) for scope, v in cells.items()},
        "asset_tf_boosted": boosted,
        "asset_tf_penalised": penalised,
        "build_seconds": scorecard["build_seconds"],
    }
    logger.info("[strategy_scorecard] rebuilt %s", json.dumps(summary, separators=(",", ":")))
    return summary


async def strategy_scorecard_loop(stop: asyncio.Event) -> None:
    interval = _env_int("STRATEGY_SCORECARD_INTERVAL_SECONDS", 3 * 3600, 600, 7 * 86400)
    retry = _env_int("STRATEGY_SCORECARD_RETRY_SECONDS", 900, 60, 86400)
    delay = _env_int("STRATEGY_SCORECARD_STARTUP_DELAY_SECONDS", 240, 0, 3600)
    try:
        await asyncio.wait_for(stop.wait(), timeout=delay)
        return
    except asyncio.TimeoutError:
        pass
    while not stop.is_set():
        wait = interval
        try:
            await rebuild_once()
        except Exception as exc:
            wait = retry
            logger.warning("[strategy_scorecard] rebuild failed error_type=%s error=%s", type(exc).__name__,
                           str(exc)[:200])
        try:
            await asyncio.wait_for(stop.wait(), timeout=wait)
        except asyncio.TimeoutError:
            pass


__all__ = [
    "REDIS_KEY",
    "adjustment_for_cell",
    "bar_index",
    "build_scorecard",
    "lookup",
    "outcome_r",
    "rebuild_once",
    "scorecard_adjustment",
    "scorecard_mode",
    "strategy_scorecard_loop",
    "wilson_interval",
]
