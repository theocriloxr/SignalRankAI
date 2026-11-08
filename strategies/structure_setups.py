"""Chart-structure setups from the owner's strategy deck (8 Nov 2026).

The owner supplied 466 annotated chart photos (TradingView, XAUUSD and Deriv
synthetic indices on 5m/15m, with MT5 position lists). The recurring setups:

1. **Zone flip retest.** Price breaks a supply (or demand) zone with an
   impulse, comes back to the broken zone and holds it; entry on the retest,
   stop just beyond the zone, targets at the swing made after the break and
   the next swings beyond it.
2. **Trendline break and retest.** A trendline through the last two swing lows
   (or highs) breaks; price retests the line from the other side; entry on the
   retest, stop above the retest swing, targets at the last swing and beyond.
3. **Channel / triangle break.** Lines through the last two swing highs and
   two swing lows contain price; a close outside with a real body is the
   entry, the stop sits back inside the channel, targets are measured moves
   of the channel height.

Everything here is additive and does not change any existing strategy. The
family runs in ``STRUCTURE_SETUPS_MODE=auto`` by default: every setup is
recorded for the shadow outcome tracker (the same path as discovered
strategies) and also offered as a candidate, which the engine's
setup-evidence filter refuses until that setup's own measured record beats its
break-even, so nothing reaches a user on an untested setup. ``shadow`` records
only; ``live`` returns candidates only; ``off`` disables them. Levels come from the chart: no target
is invented, and a setup whose structure does not offer at least 1R to TP1
is skipped.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)

GROUP = "structure_setups"
TIMEFRAMES = {"5m", "15m", "30m", "1h", "4h"}
PIVOT_SPAN = 3
LOOKBACK = 150

_seen: dict[str, float] = {}
_seen_lock = threading.Lock()


def mode() -> str:
    """``auto`` (default since 8 Nov 2026): always recorded in shadow; also offered as a candidate,
    which reaches users only once its own setup record beats break-even (engine segment-evidence
    filter). ``shadow``: recorded only. ``live``: candidate only. ``off``: nothing."""
    value = str(os.getenv("STRUCTURE_SETUPS_MODE", "auto") or "auto").strip().lower()
    return value if value in {"off", "shadow", "auto", "live"} else "auto"


def _evidence_filter_on() -> bool:
    raw = os.getenv("SEGMENT_QUARANTINE_ENABLED")
    return raw is None or str(raw).strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# candle helpers
# ---------------------------------------------------------------------------

def _bars(candles: Sequence[Mapping[str, Any]]) -> list[tuple[float, float, float, float]]:
    out: list[tuple[float, float, float, float]] = []
    for c in candles or []:
        try:
            o, h, l, cl = (float(c.get(k) if isinstance(c, Mapping) else c[i])
                           for i, k in enumerate(("open", "high", "low", "close")))
        except (TypeError, ValueError, KeyError, IndexError):
            continue
        if min(o, h, l, cl) > 0 and h >= max(o, cl) and l <= min(o, cl):
            out.append((o, h, l, cl))
    return out


def _atr(bars: list[tuple[float, float, float, float]], end: int, period: int = 14) -> float:
    start = max(1, end - period + 1)
    trs = [max(bars[i][1] - bars[i][2], abs(bars[i][1] - bars[i - 1][3]), abs(bars[i][2] - bars[i - 1][3]))
           for i in range(start, end + 1)]
    return sum(trs) / len(trs) if trs else 0.0


def _pivots(bars, lo: int, hi: int, span: int = PIVOT_SPAN) -> tuple[list[int], list[int]]:
    highs, lows = [], []
    for i in range(max(lo, span), min(hi, len(bars) - span)):
        left, right = bars[i - span:i], bars[i + 1:i + span + 1]
        # Strictly beyond the bars before, at least level with the bars after: a
        # bar opening at the previous close often shares the peak's high.
        if bars[i][1] > max(b[1] for b in left) and bars[i][1] >= max(b[1] for b in right):
            highs.append(i)
        if bars[i][2] < min(b[2] for b in left) and bars[i][2] <= min(b[2] for b in right):
            lows.append(i)
    return highs, lows


def _ladder(entry: float, risk: float, levels: list[float], is_long: bool) -> list[float]:
    """Ordered, de-duplicated chart levels at least 1R beyond entry (closer ones are skipped)."""
    sign = 1.0 if is_long else -1.0
    clean: list[float] = []
    for level in sorted({round(v, 10) for v in levels if v > 0}, reverse=not is_long):
        if sign * (level - entry) < risk:
            continue
        if clean and abs(level - clean[-1]) < 0.25 * risk:
            continue
        clean.append(level)
    if not clean or sign * (clean[0] - entry) < risk:
        return []
    return clean[:3]


def _setup(name: str, direction: str, entry: float, stop: float, targets: list[float], reason: str,
           **extra: Any) -> dict[str, Any]:
    risk = abs(entry - stop)
    return {
        "strategy_name": name, "strategy_group": GROUP, "direction": direction.upper(), "entry": entry,
        "stop": stop, "stop_loss": stop, "take_profit": targets, "targets": targets,
        "confidence": 0.6, "rr_ratio": abs(targets[0] - entry) / risk if risk > 0 else None,
        "reasoning": reason, "target_model": "chart_structure", **extra,
    }


# ---------------------------------------------------------------------------
# 1. zone flip retest
# ---------------------------------------------------------------------------

def zone_flip_retest(bars, s: int, atr: float) -> dict[str, Any] | None:
    lo = max(0, s - LOOKBACK)
    highs, lows = _pivots(bars, lo, s - 2)
    for is_long in (True, False):
        pivots = highs if is_long else lows  # a broken supply (swing high) becomes demand, and vice versa
        for p in reversed(pivots[-6:]):
            o, h, l, c = bars[p]
            z_lo, z_hi = (max(o, c), h) if is_long else (l, min(o, c))
            if z_hi - z_lo < 0.15 * atr:
                mid = (z_hi + z_lo) / 2
                z_lo, z_hi = mid - 0.15 * atr, mid + 0.15 * atr
            # The break: first close beyond the zone after the pivot, with an impulse body.
            b = next((i for i in range(p + 1, s) if (bars[i][3] > z_hi if is_long else bars[i][3] < z_lo)), None)
            if b is None or s - b > 40 or s - b < 2:
                continue
            if abs(bars[b][3] - bars[b][0]) < 0.6 * atr:
                continue
            # Held: no close back through the far side of the zone since the break.
            if any((bars[i][3] < z_lo if is_long else bars[i][3] > z_hi) for i in range(b + 1, s + 1)):
                continue
            o, h, l, c = bars[s]
            touched = (l <= z_hi + 0.1 * atr) if is_long else (h >= z_lo - 0.1 * atr)
            held = (c > z_hi) if is_long else (c < z_lo)
            if not (touched and held):
                continue
            entry = c
            stop = (z_lo - 0.25 * atr) if is_long else (z_hi + 0.25 * atr)
            risk = abs(entry - stop)
            if risk < 0.3 * atr:
                continue
            after = range(b, s)
            swing = max(bars[i][1] for i in after) if is_long else min(bars[i][2] for i in after)
            beyond = [bars[i][1] for i in highs if bars[i][1] > swing] if is_long else \
                     [bars[i][2] for i in lows if bars[i][2] < swing]
            impulse = abs(bars[b][3] - (z_lo if is_long else z_hi))
            measured = entry + (1 if is_long else -1) * max(impulse, 2 * risk)
            targets = _ladder(entry, risk, [swing, *beyond, measured], is_long)
            if not targets:
                continue
            side = "demand" if is_long else "supply"
            return _setup("Zone Flip Retest", "long" if is_long else "short", entry, stop, targets,
                          f"Broken {'supply' if is_long else 'demand'} zone {z_lo:.6g}-{z_hi:.6g} retested as {side}; "
                          f"stop beyond the zone, targets at the post-break swing and beyond.",
                          zone_low=z_lo, zone_high=z_hi)
    return None


# ---------------------------------------------------------------------------
# 2. trendline break and retest
# ---------------------------------------------------------------------------

def trendline_break_retest(bars, s: int, atr: float) -> dict[str, Any] | None:
    lo = max(0, s - LOOKBACK)
    highs, lows = _pivots(bars, lo, s - 2)
    # Rising line through two higher lows breaks down -> short; falling line through lower highs breaks up -> long.
    for is_long, pts, price_of in ((False, lows, lambda i: bars[i][2]), (True, highs, lambda i: bars[i][1])):
        # The line runs through two consecutive swings made before the break (the
        # break itself usually prints a newer swing), so try recent pairs.
        found = None
        for k in range(len(pts) - 1, max(0, len(pts) - 4), -1):
            a, b = pts[k - 1], pts[k]
            pa, pb = price_of(a), price_of(b)
            slope = (pb - pa) / (b - a)
            if (not is_long and slope <= 0) or (is_long and slope >= 0):
                continue
            line = lambda i, pb=pb, b=b, slope=slope: pb + slope * (i - b)  # noqa: E731
            brk = next((i for i in range(b + 1, s) if (bars[i][3] > line(i) if is_long else bars[i][3] < line(i))),
                       None)
            if brk is not None and 2 <= s - brk <= 30:
                found = (a, b, slope, line, brk)
                break
        if found is None:
            continue
        a, b, slope, line, brk = found
        o, h, l, c = bars[s]
        touched = (l <= line(s) + 0.15 * atr) if is_long else (h >= line(s) - 0.15 * atr)
        held = (c > line(s)) if is_long else (c < line(s))
        if not (touched and held):
            continue
        entry = c
        extreme = min(bars[i][2] for i in range(brk, s + 1)) if is_long else max(bars[i][1] for i in range(brk, s + 1))
        stop = extreme - 0.25 * atr if is_long else extreme + 0.25 * atr
        risk = abs(entry - stop)
        if risk < 0.3 * atr:
            continue
        # Targets: the swing the line was drawn from and the swings beyond it.
        if is_long:
            prior = [bars[i][1] for i in highs if i < brk and bars[i][1] > entry]
            levels = sorted(prior)[:3]
            depth = max(bars[i][1] for i in range(a, brk + 1)) - min(bars[i][2] for i in range(a, brk + 1))
        else:
            prior = [bars[i][2] for i in lows if i < brk and bars[i][2] < entry]
            levels = sorted(prior, reverse=True)[:3]
            depth = max(bars[i][1] for i in range(a, brk + 1)) - min(bars[i][2] for i in range(a, brk + 1))
        measured = entry + (1 if is_long else -1) * depth
        targets = _ladder(entry, risk, [*levels, measured], is_long)
        if not targets:
            continue
        return _setup("Trendline Break Retest", "long" if is_long else "short", entry, stop, targets,
                      f"{'Falling' if is_long else 'Rising'} trendline through swings at bars {a},{b} broke and was "
                      f"retested; stop beyond the retest swing, targets at prior swings and the measured move.",
                      trendline_slope=slope)
    return None


# ---------------------------------------------------------------------------
# 3. channel / triangle break
# ---------------------------------------------------------------------------

def channel_break(bars, s: int, atr: float) -> dict[str, Any] | None:
    lo = max(0, s - LOOKBACK)
    highs, lows = _pivots(bars, lo, s - 2)
    if len(highs) < 2 or len(lows) < 2:
        return None
    h1, h2, l1, l2 = highs[-2], highs[-1], lows[-2], lows[-1]
    up_slope = (bars[h2][1] - bars[h1][1]) / (h2 - h1)
    dn_slope = (bars[l2][2] - bars[l1][2]) / (l2 - l1)
    upper = lambda i: bars[h2][1] + up_slope * (i - h2)  # noqa: E731
    lower = lambda i: bars[l2][2] + dn_slope * (i - l2)  # noqa: E731
    start = min(h1, l1)
    height = upper(start) - lower(start)
    if height <= 2 * atr or upper(s) <= lower(s):
        return None
    # Price stayed inside the channel from its first pivot to the bar before the break.
    if any(bars[i][3] > upper(i) + 0.1 * atr or bars[i][3] < lower(i) - 0.1 * atr for i in range(start, s)):
        return None
    o, h, l, c = bars[s]
    if abs(c - o) < 0.5 * atr:
        return None
    for is_long in (True, False):
        edge = upper(s) if is_long else lower(s)
        if not ((c > edge + 0.05 * atr) if is_long else (c < edge - 0.05 * atr)):
            continue
        entry = c
        # Stop back inside the channel, a quarter of its height from the broken line.
        stop = edge - 0.25 * height if is_long else edge + 0.25 * height
        risk = abs(entry - stop)
        if risk < 0.3 * atr:
            continue
        sign = 1 if is_long else -1
        targets = _ladder(entry, risk, [edge + sign * 0.5 * height, edge + sign * height, edge + sign * 1.618 * height],
                          is_long)
        if not targets:
            continue
        shape = "triangle" if up_slope < 0 < dn_slope else "channel"
        return _setup("Channel Break", "long" if is_long else "short", entry, stop, targets,
                      f"Close {'above' if is_long else 'below'} a {shape} (height {height:.6g}); stop back inside, "
                      f"targets at 0.5, 1 and 1.618 of the height.", channel_height=height, channel_shape=shape)
    return None


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

DETECTORS = (zone_flip_retest, trendline_break_retest, channel_break)


def detect_setups(candles: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Setups on the last closed bar (the last candle may still be forming)."""
    bars = _bars(candles)
    if len(bars) < 60:
        return []
    s = len(bars) - 2
    atr = _atr(bars, s)
    if atr <= 0:
        return []
    out = []
    for detector in DETECTORS:
        try:
            found = detector(bars, s, atr)
        except (ValueError, ZeroDivisionError, IndexError):
            found = None
        if found:
            found["atr"] = atr
            out.append(found)
    return out


def _claim(key: str) -> bool:
    with _seen_lock:
        if key in _seen:
            return False
        _seen[key] = time.monotonic()
        while len(_seen) > 8192:
            _seen.pop(next(iter(_seen)))
    return True


def _record_shadow(candidate: dict[str, Any]) -> None:
    try:
        from engine.signal_deduplicator import get_ml_rejection_tracker
        from utils.async_runner import submit_background_coro

        features = {
            "rejection_type": "structure_setup_shadow",
            "strategy_name": candidate["strategy_name"],
            "strategy_group": GROUP,
            "rr_ratio": candidate.get("rr_ratio"),
            "source": "structure_setup_shadow",
        }
        coro = get_ml_rejection_tracker().persist_rejection(
            asset=candidate["asset"], timeframe=candidate["timeframe"], direction=candidate["direction"].lower(),
            entry_price=candidate["entry"], stop_loss=candidate["stop"], take_profit_levels=list(candidate["targets"]),
            ml_probability=None, rejection_reason="structure_setup_shadow", features=features,
            rejection_type="structure_setup_shadow",
        )
        submit_background_coro(coro, label="structure_setup_shadow")
    except Exception:
        logger.debug("[structure_setups] shadow record failed", exc_info=True)


def structure_setup_candidates(asset: str, timeframe: str, data: Mapping[str, Any]) -> list[dict[str, Any]]:
    current = mode()
    tf = str(timeframe or "").lower()
    if current == "off" or tf not in TIMEFRAMES:
        return []
    candles = (data or {}).get("candles") or []
    out = []
    for setup in detect_setups(candles):
        setup.update(asset=str(asset).upper(), symbol=str(asset).upper(), timeframe=tf, strength=0.6)
        key = f"{asset}|{tf}|{setup['strategy_name']}|{setup['direction']}|{len(candles)}|{setup['entry']:.10g}"
        if not _claim(key):
            continue
        if current == "live":
            out.append(setup)
            continue
        _record_shadow(setup)
        # auto: the owner's rule (8 Nov 2026) "live only once the record is good",
        # per setup: the engine's segment-evidence filter refuses a setup whose
        # measured TP1 rate does not beat its break-even. Without that filter,
        # stay shadow-only.
        if current == "auto" and _evidence_filter_on():
            out.append(dict(setup))
    return out


__all__ = ["GROUP", "detect_setups", "structure_setup_candidates", "zone_flip_retest", "trendline_break_retest",
           "channel_break", "mode"]
