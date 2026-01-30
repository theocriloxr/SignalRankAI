from typing import Iterable, List

from engine.signal import Signal


def run_strategy_with_marketstate(strategy, asset: str, timeframes: Iterable[str], include_ml: bool = False) -> List[Signal]:
    """Fetch market state for `asset` and invoke `strategy.generate`.

    `strategy` may be a Strategy instance or any object with `generate(market_data)`.
    """
    try:
        from engine.market_state import get_market_state
    except Exception:
        return []

    ms = get_market_state(asset, timeframes, include_ml=include_ml)
    # Strategy expects `timeframes` -> payload mapping; provide both top-level and nested
    tf_payload = ms.get("timeframes", {})
    # Some older strategies may expect 'asset' inside payloads; ensure asset present
    for tf, p in tf_payload.items():
        if isinstance(p, dict) and "asset" not in p:
            p["asset"] = asset

    try:
        out = strategy.generate(tf_payload)
        return out or []
    except Exception:
        return []
