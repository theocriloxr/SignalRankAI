"""Top-down supply/demand order-block entries (owner-supplied strategy videos).

Sources: two owner screen recordings, 23 Jun 2026 (XAUUSD) and 6 Aug 2026
(USDCAD), reviewed on 28 Oct 2026 from extracted frames and a machine
transcript. The first recording's audio is unusable; the second narrates
timeframe alignment (weekly, daily, 4 hours), selling from the premium zone
"down to possibly 50%", a 4h ABC structure confirmed when price takes and
breaks the low, and a 15m entry only once price breaks "this initial ABC low".
As implemented:

1. Higher timeframe (1d, else 4h): the base candle immediately before a strong
   displacement is the order block: supply before a bearish leg, demand before
   a bullish one. Only zones price has not returned to are fresh.
2. Premium/discount: the dealing range is the 1d high/low (weekly candles are
   not available to the engine). Sells only above its 50% equilibrium, buys
   only below it.
3. 4h structure: after the zone formed, price closed through the previous 4h
   swing in the displacement direction (break of structure).
4. 15m (else 5m; the recording used 3m): inside the zone price prints an ABC
   (A swing, B opposite swing, C beyond A taking A's liquidity) and the latest
   closed bar is the first to close through B. That close is the entry.
5. Stop beyond C plus an ATR buffer. Target the nearer of the equilibrium and
   the 4h liquidity the break of structure left behind, never below ``min_rr``.

Every function reads closed candles only. The strategy is disabled unless
``ZONE_REJECTION_STRATEGY_ENABLED`` is set, so it cannot reach live signal
generation before the owner approves backtest and shadow evidence.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from engine.adaptive.data_quality import candle_timestamp
from utils.timeutils import now_utc_naive

logger = logging.getLogger(__name__)

STRATEGY_NAME = "Order Block ABC (Top-Down)"
STRATEGY_VERSION = "order-block-abc-v1"
HTF_ORDER = ("1d", "4h")
EXEC_ORDER = ("15m", "5m")
_BAR_MS = {"5m": 300_000, "15m": 900_000, "4h": 14_400_000, "1d": 86_400_000}
_4H_PER_DAY = 6


@dataclass(frozen=True, slots=True)
class ZoneConfig:
    atr_period: int = 14
    displacement_atr: float = 1.5      # body of the impulse leg, in ATR
    impulse_bars: int = 3              # bars counted as one impulse leg
    swing_window: int = 2              # fractal half-width for swing points
    sweep_lookback: int = 30           # execution bars searched for the ABC
    range_bars: int = 60               # 1d bars forming the dealing range
    stop_buffer_atr: float = 0.25
    min_rr: float = 2.0
    min_candles: int = 40


@dataclass(frozen=True, slots=True)
class Zone:
    kind: str          # "supply" | "demand"
    low: float
    high: float
    created_index: int
    timeframe: str


def enabled(environment: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environment is None else environment
    return str(env.get("ZONE_REJECTION_STRATEGY_ENABLED", "0")).strip().lower() in {"1", "true", "yes", "on"}


def _ohlc(candles: Sequence[Mapping[str, Any]]) -> list[tuple[float, float, float, float]]:
    rows = []
    for candle in candles:
        try:
            o, h, l, c = (float(candle[k]) for k in ("open", "high", "low", "close"))
        except (KeyError, TypeError, ValueError):
            return []
        if not (l <= min(o, c) <= max(o, c) <= h) or l <= 0:
            return []
        rows.append((o, h, l, c))
    return rows


def atr(rows: Sequence[tuple[float, float, float, float]], period: int) -> float:
    if len(rows) < period + 1:
        return 0.0
    ranges = []
    for i in range(len(rows) - period, len(rows)):
        _, h, l, _ = rows[i]
        prev_close = rows[i - 1][3]
        ranges.append(max(h - l, abs(h - prev_close), abs(l - prev_close)))
    return sum(ranges) / period


def swing_points(rows: Sequence[tuple[float, float, float, float]], window: int) -> tuple[list[int], list[int]]:
    """Confirmed fractal highs/lows: an index needs ``window`` closed bars on both sides."""
    highs, lows = [], []
    for i in range(window, len(rows) - window):
        h, l = rows[i][1], rows[i][2]
        side = rows[i - window:i] + rows[i + 1:i + window + 1]
        if all(h > r[1] for r in side):
            highs.append(i)
        if all(l < r[2] for r in side):
            lows.append(i)
    return highs, lows


def find_fresh_zones(rows: Sequence[tuple[float, float, float, float]], timeframe: str, cfg: ZoneConfig) -> list[Zone]:
    """Base candle before a displacement leg, kept only while price has not returned to it."""
    volatility = atr(rows, cfg.atr_period)
    if volatility <= 0:
        return []
    zones: list[Zone] = []
    last = len(rows) - 1
    for i in range(1, len(rows) - cfg.impulse_bars):
        base_o, base_h, base_l, base_c = rows[i - 1]
        leg = rows[i:i + cfg.impulse_bars]
        move = leg[-1][3] - leg[0][0]
        if abs(move) < cfg.displacement_atr * volatility:
            continue
        kind = "supply" if move < 0 else "demand"
        # The base is the last opposite candle before the leg (an up-close before a drop).
        if (kind == "supply" and base_c < base_o) or (kind == "demand" and base_c > base_o):
            continue
        end = i + cfg.impulse_bars
        later = rows[end:last]  # exclude the bar now being evaluated
        touched = any(r[1] >= base_l for r in later) if kind == "supply" else any(r[2] <= base_h for r in later)
        if not touched:
            zones.append(Zone(kind, base_l, base_h, i - 1, timeframe))
    return zones


def structure_broke(rows: Sequence[tuple[float, float, float, float]], zone: Zone, cfg: ZoneConfig) -> float | None:
    """Return the swing extreme broken after the zone formed (the target liquidity), or None."""
    highs, lows = swing_points(rows, cfg.swing_window)
    after = zone.created_index + 1
    if zone.kind == "supply":
        prior = [i for i in lows if i <= after]
        if not prior:
            return None
        level = rows[prior[-1]][2]
        broken = [r[3] for r in rows[after:] if r[3] < level]
        return min(r[2] for r in rows[after:]) if broken else None
    prior = [i for i in highs if i <= after]
    if not prior:
        return None
    level = rows[prior[-1]][1]
    broken = [r[3] for r in rows[after:] if r[3] > level]
    return max(r[1] for r in rows[after:]) if broken else None


def execution_trigger(rows: Sequence[tuple[float, float, float, float]], zone: Zone, cfg: ZoneConfig) -> dict | None:
    """ABC inside the zone, and the latest closed bar is the first close through B."""
    if len(rows) < cfg.swing_window * 2 + 4:
        return None
    window = list(rows[-cfg.sweep_lookback - 1:-1])
    highs, lows = swing_points(window, cfg.swing_window)
    o, h, l, c = rows[-1]
    prev_close = window[-1][3]
    if zone.kind == "supply" and len(highs) >= 2 and lows:
        c_idx = highs[-1]
        b_idx = max((i for i in lows if i < c_idx), default=None)
        a_idx = max((i for i in highs if b_idx is not None and i < b_idx), default=None)
        if b_idx is None or a_idx is None:
            return None
        a_high, b_low, c_high = window[a_idx][1], window[b_idx][2], window[c_idx][1]
        after_c = [r[3] for r in window[c_idx + 1:]]
        in_zone = zone.low <= c_high and a_high <= zone.high
        first_break = c < b_low and prev_close >= b_low and all(x >= b_low for x in after_c)
        if c_high > a_high and in_zone and first_break and c < o:
            extreme = max([h] + [r[1] for r in window[c_idx:]])  # beyond any high since C
            return {"direction": "SHORT", "entry": c, "extreme": extreme, "swept_level": a_high,
                    "abc": (a_high, b_low, c_high)}
    if zone.kind == "demand" and len(lows) >= 2 and highs:
        c_idx = lows[-1]
        b_idx = max((i for i in highs if i < c_idx), default=None)
        a_idx = max((i for i in lows if b_idx is not None and i < b_idx), default=None)
        if b_idx is None or a_idx is None:
            return None
        a_low, b_high, c_low = window[a_idx][2], window[b_idx][1], window[c_idx][2]
        after_c = [r[3] for r in window[c_idx + 1:]]
        in_zone = c_low <= zone.high and a_low >= zone.low
        first_break = c > b_high and prev_close <= b_high and all(x <= b_high for x in after_c)
        if c_low < a_low and in_zone and first_break and c > o:
            extreme = min([l] + [r[2] for r in window[c_idx:]])  # beyond any low since C
            return {"direction": "LONG", "entry": c, "extreme": extreme, "swept_level": a_low,
                    "abc": (a_low, b_high, c_low)}
    return None


def dealing_range(rows: Sequence[tuple[float, float, float, float]], bars: int) -> tuple[float, float] | None:
    recent = rows[-bars:]
    if len(recent) < 10:
        return None
    return min(r[2] for r in recent), max(r[1] for r in recent)


def _candles(market_data: Mapping[str, Any], timeframe: str) -> list:
    data = market_data.get(timeframe)
    return list((data or {}).get("candles") or []) if isinstance(data, Mapping) else []


def _closed(candles: Sequence[Mapping[str, Any]], timeframe: str,
            now_ms: int | None) -> tuple[list, list[int | None]]:
    """OHLC rows with epoch-ms open times; with ``now_ms``, only the bars closed by then.

    Providers return the forming bar last. Closure is provable only from a bar's
    open time, so a missing open time yields nothing when closure is required.
    """
    rows = _ohlc(candles)
    stamps = [candle_timestamp(c) for c in candles] if rows else []
    if now_ms is None or not rows:
        return rows, stamps
    if any(stamp is None for stamp in stamps):
        return [], []
    keep = len(rows)
    while keep and stamps[keep - 1] + _BAR_MS[timeframe] > now_ms:
        keep -= 1
    return rows[:keep], stamps[:keep]


def _pick(market_data: Mapping[str, Any], order: Sequence[str], minimum: int,
          now_ms: int | None = None) -> tuple[str | None, list, list]:
    for tf in order:
        rows, stamps = _closed(_candles(market_data, tf), tf, now_ms)
        if len(rows) >= minimum:
            return tf, rows, stamps
    return None, [], []


def map_index(source_stamps: Sequence[Any], index: int, target_stamps: Sequence[Any]) -> int | None:
    """First target bar opening at or after the source bar's open; None without comparable stamps."""
    try:
        stamp = source_stamps[index]
        if stamp is None:
            return None
        return next((i for i, other in enumerate(target_stamps) if other is not None and other >= stamp), None)
    except (IndexError, TypeError):
        return None


def structure_index(htf_stamps: Sequence[Any], index: int, structure_stamps: Sequence[Any]) -> int | None:
    """Last 4h bar inside the HTF base bar (the zone forms at its close); None unless 4h history covers it."""
    try:
        if htf_stamps[index] is None or structure_stamps[0] is None or structure_stamps[0] > htf_stamps[index]:
            return None
    except (IndexError, TypeError):
        return None
    following = map_index(htf_stamps, index + 1, structure_stamps)
    return following - 1 if following else None


def _epoch_ms(moment: datetime) -> int:
    aware = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return int(aware.timestamp() * 1000)


def zone_rejection_strategies(asset: str, market_data: Mapping[str, Any],
                              environment: Mapping[str, str] | None = None,
                              config: ZoneConfig | None = None,
                              now: datetime | None = None) -> list[dict[str, Any]]:
    """``now`` (UTC, default the current time) decides which execution and 4h bars have closed."""
    if not enabled(environment):
        return []
    cfg = config or ZoneConfig()
    try:
        now_ms = _epoch_ms(now if now is not None else now_utc_naive())
        # The HTF keeps its forming bar: it is the bar under evaluation, never counted as a touch.
        htf, htf_rows, htf_stamps = _pick(market_data, HTF_ORDER, cfg.min_candles)
        exec_tf, exec_rows, _ = _pick(market_data, EXEC_ORDER, cfg.min_candles, now_ms)
        structure_rows, structure_stamps = _closed(_candles(market_data, "4h"), "4h", now_ms)
        if not htf or not exec_tf or len(structure_rows) < cfg.min_candles:
            return []
        exec_atr = atr(exec_rows, cfg.atr_period)
        daily_rows = _ohlc(_candles(market_data, "1d"))
        # range_bars counts days; without daily candles the 4h range spans the same days.
        dealing = (dealing_range(daily_rows, cfg.range_bars) if daily_rows
                   else dealing_range(htf_rows, cfg.range_bars * _4H_PER_DAY))
        if exec_atr <= 0 or dealing is None or dealing[1] <= dealing[0]:
            return []
        out = []
        for zone in find_fresh_zones(htf_rows, htf, cfg):
            # Locate the zone's base candle on the 4h chart by time; skip when that is not provable.
            created = (zone.created_index if htf == "4h"
                       else structure_index(htf_stamps, zone.created_index, structure_stamps))
            if created is None:
                continue
            target = structure_broke(structure_rows, Zone(zone.kind, zone.low, zone.high, created, "4h"), cfg)
            trigger = execution_trigger(exec_rows, zone, cfg) if target is not None else None
            if not trigger:
                continue
            entry = trigger["entry"]
            equilibrium = (dealing[0] + dealing[1]) / 2.0
            if trigger["direction"] == "SHORT":
                if entry <= equilibrium:
                    continue  # sells only from the premium half of the range
                target = max(target, equilibrium)
                stop = trigger["extreme"] + cfg.stop_buffer_atr * exec_atr
                risk, reward = stop - entry, entry - target
            else:
                if entry >= equilibrium:
                    continue  # buys only from the discount half of the range
                target = min(target, equilibrium)
                stop = trigger["extreme"] - cfg.stop_buffer_atr * exec_atr
                risk, reward = entry - stop, target - entry
            if risk <= 0 or reward <= 0 or reward / risk < cfg.min_rr:
                continue
            rr = round(reward / risk, 2)
            out.append({
                "asset": asset, "symbol": asset, "timeframe": exec_tf, "direction": trigger["direction"],
                "entry": float(entry), "stop_loss": float(stop), "take_profit": float(target),
                "rr_ratio": rr, "confidence": 0.8, "strength": 0.8, "grade": "B",
                "strategy_name": STRATEGY_NAME, "strategy_group": "zones", "strategy_version": STRATEGY_VERSION,
                "reasoning": (
                    f"{zone.timeframe} {zone.kind} order block {zone.low:.5g}-{zone.high:.5g} in the "
                    + ("premium" if trigger["direction"] == "SHORT" else "discount")
                    + f" half of the range; 4h structure broke; {exec_tf} ABC took {trigger['swept_level']:.5g} "
                    + f"and closed through B {trigger['abc'][1]:.5g}."
                ),
                "equilibrium": float(equilibrium),
                "zone_low": float(zone.low), "zone_high": float(zone.high), "zone_timeframe": zone.timeframe,
                "swept_level": float(trigger["swept_level"]), "source": "zone_rejection",
                "market_open_confirmed": True, "created_at": now_utc_naive(),
            })
        return out
    except Exception:
        logger.exception("Zone rejection strategy failed asset=%s", asset)
        return []


__all__ = ["STRATEGY_NAME", "STRATEGY_VERSION", "Zone", "ZoneConfig", "enabled", "execution_trigger",
           "dealing_range", "find_fresh_zones", "map_index", "structure_broke", "structure_index",
           "swing_points", "zone_rejection_strategies"]
