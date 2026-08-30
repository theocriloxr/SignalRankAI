from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .types import DataQualityReport, safe_float

_TIMEFRAME_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800}


def candle_timestamp(candle: Mapping[str, Any]) -> int | None:
    for key in ("open_time_ms", "timestamp_ms", "time_ms", "close_time_ms"):
        raw = candle.get(key)
        if raw is not None:
            try:
                value = int(float(raw))
                return value if value > 10_000_000_000 else value * 1000
            except (TypeError, ValueError):
                pass
    for key in ("timestamp", "time", "datetime", "date"):
        raw = candle.get(key)
        if raw is None:
            continue
        if isinstance(raw, datetime):
            dt = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        try:
            value = float(raw)
            return int(value if value > 10_000_000_000 else value * 1000)
        except (TypeError, ValueError):
            try:
                dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return int(dt.timestamp() * 1000)
            except Exception:
                continue
    return None


def normalise_candles(candles: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for candle in candles or ():
        if not isinstance(candle, Mapping):
            continue
        row = dict(candle)
        row["open"] = safe_float(candle.get("open"))
        row["high"] = safe_float(candle.get("high"))
        row["low"] = safe_float(candle.get("low"))
        row["close"] = safe_float(candle.get("close"))
        row["volume"] = max(0.0, safe_float(candle.get("volume")))
        ts = candle_timestamp(candle)
        if ts is not None:
            row["open_time_ms"] = ts
        output.append(row)
    output.sort(key=lambda c: int(c.get("open_time_ms") or 0))
    return output


def assess_candle_quality(
    candles: Iterable[Mapping[str, Any]],
    *,
    timeframe: str,
    provider: str = "unknown",
    data_age_seconds: float | None = None,
    minimum_candles: int = 30,
) -> DataQualityReport:
    rows = normalise_candles(candles)
    duplicate_count = impossible_count = missing_count = gap_count = 0
    seen: set[int] = set()
    expected_ms = int(_TIMEFRAME_SECONDS.get(str(timeframe).lower(), 3600) * 1000)
    last_ts: int | None = None
    for row in rows:
        o, h, l, c = (safe_float(row.get(x)) for x in ("open", "high", "low", "close"))
        if min(o, h, l, c) <= 0:
            missing_count += 1
        if h < max(o, c, l) or l > min(o, c, h):
            impossible_count += 1
        ts = row.get("open_time_ms")
        if ts:
            ts = int(ts)
            if ts in seen:
                duplicate_count += 1
            seen.add(ts)
            if last_ts and expected_ms and ts - last_ts > expected_ms * 1.8:
                gap_count += max(1, int(round((ts - last_ts) / expected_ms)) - 1)
            last_ts = ts
    stale_limit = _TIMEFRAME_SECONDS.get(str(timeframe).lower(), 3600) * 2.5
    stale = data_age_seconds is not None and float(data_age_seconds) > stale_limit
    reasons: list[str] = []
    if len(rows) < minimum_candles:
        reasons.append(f"insufficient_candles:{len(rows)}<{minimum_candles}")
    if stale:
        reasons.append("stale_candles")
    if impossible_count:
        reasons.append(f"impossible_ohlc:{impossible_count}")
    if missing_count:
        reasons.append(f"missing_prices:{missing_count}")
    if duplicate_count:
        reasons.append(f"duplicates:{duplicate_count}")
    if gap_count:
        reasons.append(f"gaps:{gap_count}")
    penalties = (
        min(0.45, impossible_count * 0.10)
        + min(0.25, missing_count * 0.05)
        + min(0.15, duplicate_count * 0.02)
        + min(0.20, gap_count * 0.02)
        + (0.35 if stale else 0.0)
        + (0.30 if len(rows) < minimum_candles else 0.0)
    )
    score = max(0.0, min(1.0, 1.0 - penalties))
    usable = score >= 0.60 and len(rows) >= minimum_candles and impossible_count == 0 and not stale
    return DataQualityReport(
        usable=usable,
        score=score,
        candle_count=len(rows),
        stale=stale,
        duplicate_count=duplicate_count,
        gap_count=gap_count,
        impossible_count=impossible_count,
        missing_count=missing_count,
        provider=str(provider or "unknown"),
        reasons=tuple(reasons),
    )
