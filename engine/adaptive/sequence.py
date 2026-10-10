from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping
from .data_quality import candle_timestamp, normalise_candles


def sequence_reference(
    asset: str, timeframe: str, tf_data: Mapping[str, Any], *, pre_signal_candles: int = 120
) -> dict[str, Any]:
    # This records when the input was actually present in this process. Provider
    # publication/revision time is separate and must never be inferred from it.
    captured_at = datetime.now(timezone.utc).isoformat()
    raw_candles = tf_data.get("candles") or []
    # Legacy timestamp aliases may denote closes. Do not invent an open-time
    # convention merely because normalization creates an open_time_ms alias.
    explicit_opens = bool(raw_candles) and all(isinstance(c, Mapping) and c.get("open_time_ms") is not None for c in raw_candles)
    candles = normalise_candles(raw_candles)[-max(20, pre_signal_candles) :]
    canonical = [{k: c.get(k) for k in ("open_time_ms", "open", "high", "low", "close", "volume")} for c in candles]
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    closes = [float(c.get("close") or 0) for c in candles]
    highs = [float(c.get("high") or 0) for c in candles]
    lows = [float(c.get("low") or 0) for c in candles]
    return {
        "asset": str(asset).upper(),
        "timeframe": str(timeframe).lower(),
        "sequence_hash": digest,
        "candle_count": len(candles),
        "start_time_ms": candle_timestamp(candles[0]) if candles else None,
        "end_time_ms": candle_timestamp(candles[-1]) if candles else None,
        "provider": str(tf_data.get("source") or tf_data.get("provider") or "unknown"),
        "summary": {
            "captured_at": captured_at,
            "timestamp_convention": "bar_open" if explicit_opens else "unverified",
            "publication_vintage": "unverified",
            "first_close": closes[0] if closes else None,
            "last_close": closes[-1] if closes else None,
            "highest": max(highs) if highs else None,
            "lowest": min(lows) if lows else None,
            "data_age_seconds": tf_data.get("data_age_seconds"),
        },
        "evidence_stage": "pre_signal",
    }
