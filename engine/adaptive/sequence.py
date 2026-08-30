from __future__ import annotations

import hashlib, json
from typing import Any, Mapping
from .data_quality import candle_timestamp, normalise_candles


def sequence_reference(asset: str, timeframe: str, tf_data: Mapping[str, Any], *, pre_signal_candles: int = 120) -> dict[str, Any]:
    candles=normalise_candles(tf_data.get("candles") or [])[-max(20,pre_signal_candles):]
    canonical=[{k:c.get(k) for k in ("open_time_ms","open","high","low","close","volume")} for c in candles]
    digest=hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
    closes=[float(c.get("close") or 0) for c in candles]
    highs=[float(c.get("high") or 0) for c in candles]
    lows=[float(c.get("low") or 0) for c in candles]
    return {"asset":str(asset).upper(),"timeframe":str(timeframe).lower(),"sequence_hash":digest,"candle_count":len(candles),"start_time_ms":candle_timestamp(candles[0]) if candles else None,"end_time_ms":candle_timestamp(candles[-1]) if candles else None,"provider":str(tf_data.get("source") or tf_data.get("provider") or "unknown"),"summary":{"first_close":closes[0] if closes else None,"last_close":closes[-1] if closes else None,"highest":max(highs) if highs else None,"lowest":min(lows) if lows else None,"data_age_seconds":tf_data.get("data_age_seconds")},"evidence_stage":"pre_signal"}
