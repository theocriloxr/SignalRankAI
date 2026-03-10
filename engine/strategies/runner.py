import asyncio
from typing import Iterable, List, Any

from engine.signal import Signal


def run_strategy_with_marketstate(strategy: Any, asset: str, timeframes: Iterable[str], include_ml: bool = False) -> List[Signal]:
    """Sync runner: call async `get_market_state` safely and invoke strategy.generate.

    Keeps backward compatibility for sync code paths by using the sync wrapper
    exposed by `engine.market_state`.
    """
    try:
        from engine.market_state import get_market_state_sync
    except Exception:
        return []

    ms = get_market_state_sync(asset, timeframes, include_ml=include_ml)
    tf_payload = ms.get("timeframes", {})
    for tf, p in tf_payload.items():
        if isinstance(p, dict) and "asset" not in p:
            p["asset"] = asset

    try:
        out = strategy.generate(tf_payload)
        out = out or []
        # Persist decision log if DB available
        try:
            from db import repository as repo
            # Run DB persist in a background task if possible
            try:
                # best-effort: don't block strategy execution
                import asyncio as _asyncio
                _asyncio.get_event_loop().create_task(repo.persist_decision_log(None, None, None, "issued", reason=None, meta={"asset": asset, "signals": len(out)}))
            except Exception:
                # Fallback: synchronous attempt (will likely raise without session)
                pass
        except Exception:
            pass
        return out
    except Exception:
        return []


async def run_strategy_with_marketstate_async(strategy: Any, asset: str, timeframes: Iterable[str], include_ml: bool = False) -> List[Signal]:
    """Async runner: await `get_market_state` and invoke strategy.generate in thread if it's sync."""
    try:
        # Prefer the explicit async variant to avoid awaiting a sync wrapper
        from engine.market_state import get_market_state_async as get_market_state
    except Exception:
        return []

    ms = await get_market_state(asset, timeframes, include_ml=include_ml)
    tf_payload = ms.get("timeframes", {})
    for tf, p in tf_payload.items():
        if isinstance(p, dict) and "asset" not in p:
            p["asset"] = asset

    # If strategy.generate is async, await it; otherwise run in thread
    gen = getattr(strategy, "generate", None)
    if gen is None:
        return []
    if asyncio.iscoroutinefunction(gen):
        try:
            out = await gen(tf_payload) or []
            try:
                from db import repository as repo
                try:
                    import asyncio as _asyncio
                    _asyncio.get_event_loop().create_task(repo.persist_decision_log(None, None, None, "issued", reason=None, meta={"asset": asset, "signals": len(out)}))
                except Exception:
                    pass
            except Exception:
                pass
            return out
        except Exception:
            return []
    else:
        try:
            # run sync generate in thread
            out = await asyncio.to_thread(gen, tf_payload) or []
            try:
                from db import repository as repo
                try:
                    import asyncio as _asyncio
                    _asyncio.get_event_loop().create_task(repo.persist_decision_log(None, None, None, "issued", reason=None, meta={"asset": asset, "signals": len(out)}))
                except Exception:
                    pass
            except Exception:
                pass
            return out
        except Exception:
            return []
