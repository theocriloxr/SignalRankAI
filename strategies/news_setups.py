"""Technical news trading: the post-release range breakout (23 Nov 2026).

The engine never trades *into* a high-impact release: setups within 60 minutes of it are
rejected with ``news_window`` and tracked to their outcome. What happens *after* the release is
tradable, and this is the standard way to trade it on the chart instead of guessing the number:

1. The release range: the high and low of the bars in the first ``RANGE_MINUTES`` after the
   release time (the initial reaction, often a spike both ways).
2. Impulse filter: the range must be at least ``MIN_RANGE_ATR`` times the pre-release ATR
   (a release the market ignored is not traded), and at most ``MAX_RANGE_ATR`` (a disorderly
   spike gives a stop too wide to size).
3. Breakout: the last closed bar is the *first* close beyond the range high (long) or low
   (short) after the range formed, in the direction of the release bar's own move
   (continuation, not fade), within ``MAX_MINUTES_AFTER`` of the release.
4. Risk: stop at the range midpoint (the breakout is wrong if price returns into the middle of
   the reaction); targets at 1.5R, 2.5R and 4R.

Only 5m and 15m bars can see the release range. The setup goes through the same gates and
tracking as every other strategy: while it is inside the engine's 60-minute news window it is
rejected and tracked (so its record builds up honestly), and it reaches users only through the
same evidence and ML gates. Nothing here loosens a gate.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

NAME = "News Release Breakout"
TIMEFRAMES = {"5m", "15m"}
RANGE_MINUTES = 15
MIN_RANGE_ATR = 1.0
MAX_RANGE_ATR = 4.0
MAX_MINUTES_AFTER = 150


def _ts(candle: Mapping[str, Any]) -> float | None:
    for key in ("timestamp", "time", "open_time", "t", "datetime", "date"):
        value = candle.get(key) if isinstance(candle, Mapping) else None
        if value is None:
            continue
        try:
            num = float(value)
            return num / 1000.0 if num > 1e11 else num
        except (TypeError, ValueError):
            try:
                stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                return (stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)).timestamp()
            except ValueError:
                continue
    return None


def _ohlc(candle: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    try:
        o, h, l, c = (float(candle[k]) for k in ("open", "high", "low", "close"))
    except (KeyError, TypeError, ValueError):
        return None
    return (o, h, l, c) if min(o, h, l, c) > 0 and h >= max(o, c) and l <= min(o, c) else None


def release_range_breakout(candles: Sequence[Mapping[str, Any]], event_time: datetime, *,
                           tf_seconds: int, now: datetime | None = None) -> dict[str, Any] | None:
    """The post-release breakout on the last closed bar, or None."""
    rows = []
    for c in candles or []:
        ts, bar = _ts(c), _ohlc(c)
        if ts is not None and bar is not None:
            rows.append((ts, *bar))
    if len(rows) < 30:
        return None
    rows.sort()
    event = (event_time if event_time.tzinfo else event_time.replace(tzinfo=timezone.utc)).timestamp()
    now_ts = (now or datetime.now(timezone.utc)).timestamp()
    if not 0 < now_ts - event <= MAX_MINUTES_AFTER * 60:
        return None
    # The last *closed* bar: its period has ended.
    closed = [r for r in rows if r[0] + tf_seconds <= now_ts]
    if not closed:
        return None
    last = closed[-1]
    range_end = event + RANGE_MINUTES * 60
    window = [r for r in closed if event <= r[0] < range_end]
    before = [r for r in closed if r[0] < event]
    after = [r for r in closed if r[0] >= range_end]
    if not window or len(before) < 15 or not after or last[0] < range_end:
        return None
    trs = [max(b[2] - b[3], abs(b[2] - a[4]), abs(b[3] - a[4])) for a, b in zip(before[-15:-1], before[-14:])]
    atr = sum(trs) / len(trs) if trs else 0.0
    hi, lo = max(r[2] for r in window), min(r[3] for r in window)
    width = hi - lo
    if atr <= 0 or not MIN_RANGE_ATR * atr <= width <= MAX_RANGE_ATR * atr:
        return None
    impulse_up = window[-1][4] > window[0][1]  # release window closed above where it opened
    close = last[4]
    is_long = close > hi
    is_short = close < lo
    if not (is_long or is_short) or (is_long and not impulse_up) or (is_short and impulse_up):
        return None
    # First close beyond the range since it formed.
    for r in after[:-1]:
        if (is_long and r[4] > hi) or (is_short and r[4] < lo):
            return None
    mid = (hi + lo) / 2.0
    risk = abs(close - mid)
    if risk <= 0 or risk > 2.5 * atr:
        return None
    sign = 1.0 if is_long else -1.0
    targets = [close + sign * k * risk for k in (1.5, 2.5, 4.0)]
    return {
        "strategy_name": NAME, "strategy_group": "news_setups", "direction": "LONG" if is_long else "SHORT",
        "entry": close, "stop": mid, "stop_loss": mid, "take_profit": targets, "targets": targets,
        "confidence": 0.6, "rr_ratio": 1.5, "target_model": "news_release_range", "atr": atr,
        "release_range": {"high": hi, "low": lo, "width_atr": round(width / atr, 2)},
        "minutes_after_release": round((now_ts - event) / 60.0, 1),
        "reasoning": (f"Post-release breakout: first close {'above' if is_long else 'below'} the "
                      f"{RANGE_MINUTES}-minute release range ({width / atr:.1f} ATR wide), in the direction of "
                      f"the release move; stop at the range midpoint."),
    }


def _mode() -> str:
    value = str(os.getenv("NEWS_SETUPS_MODE", "auto") or "auto").strip().lower()
    return value if value in {"off", "shadow", "auto", "live"} else "auto"


def news_setup_candidates(asset: str, timeframe: str, data: Mapping[str, Any]) -> list[dict[str, Any]]:
    tf = str(timeframe or "").lower()
    if _mode() == "off" or tf not in TIMEFRAMES:
        return []
    try:
        from services.economic_calendar import news_window_event_sync

        event = news_window_event_sync(asset, buffer_minutes=MAX_MINUTES_AFTER)
    except Exception:
        return []
    if not event or not event.get("event_time") or float(event.get("minutes_from_event") or 0) <= RANGE_MINUTES:
        return []
    try:
        event_time = datetime.fromisoformat(str(event["event_time"]))
    except ValueError:
        return []
    setup = release_range_breakout((data or {}).get("candles") or [], event_time,
                                   tf_seconds=300 if tf == "5m" else 900)
    if not setup:
        return []
    setup.update(asset=str(asset).upper(), symbol=str(asset).upper(), timeframe=tf, strength=0.6,
                 news_event=str(event.get("title") or "")[:80])
    from strategies.structure_setups import _claim, _evidence_filter_on, _record_shadow

    key = f"{asset}|{tf}|{NAME}|{setup['direction']}|{setup['entry']:.10g}"
    if not _claim(key):
        return []
    mode = _mode()
    if mode != "live":
        _record_shadow(setup)
    # auto: offered only behind the engine's segment-evidence filter, like the structure setups.
    return [setup] if mode == "live" or (mode == "auto" and _evidence_filter_on()) else []


__all__ = ["NAME", "release_range_breakout", "news_setup_candidates"]
