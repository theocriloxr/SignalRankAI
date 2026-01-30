"""Engine loop: async runner that periodically runs strategies over assets."""
import asyncio
import logging
import os
from typing import Iterable, List, Dict

from utils.async_runner import run_sync
from engine.strategies.commodity import CommodityStrategy
from engine.strategies.runner import run_strategy_with_marketstate_async

logger = logging.getLogger(__name__)


async def run_once(assets: Iterable[str], timeframes: Iterable[str], include_ml: bool = False) -> Dict[str, List]:
    """Run one cycle across assets and strategies; returns mapping asset->signals."""
    results = {}
    strat = CommodityStrategy()
    tasks = []
    for a in assets:
        tasks.append(asyncio.create_task(run_strategy_with_marketstate_async(strat, a, timeframes, include_ml=include_ml)))

    done = await asyncio.gather(*tasks, return_exceptions=True)
    for asset, res in zip(assets, done):
        if isinstance(res, Exception):
            logger.exception("strategy run failed for %s", asset)
            results[asset] = []
        else:
            results[asset] = res or []
    return results


async def main_loop(assets: Iterable[str], timeframes: Iterable[str], include_ml: bool = False, interval_seconds: int = 300):
    logger.info("engine loop starting assets=%s tf=%s interval=%s", assets, timeframes, interval_seconds)
    while True:
        try:
            res = await run_once(assets, timeframes, include_ml=include_ml)
            logger.info("engine cycle completed: %s", {k: len(v) for k, v in res.items()})
        except Exception:
            logger.exception("engine main loop failed")
        await asyncio.sleep(interval_seconds)


def start_engine_loop(assets: Iterable[str], timeframes: Iterable[str], include_ml: bool = False, interval_seconds: int = 300):
    """Sync entrypoint to run the async main loop using `run_sync` shim."""
    return run_sync(main_loop(assets, timeframes, include_ml=include_ml, interval_seconds=interval_seconds))


def demo_start():
    assets = (os.getenv("DEMO_ASSETS") or "XAUUSD").split(",")
    timeframes = (os.getenv("DEMO_TIMEFRAMES") or "1h,1d").split(",")
    start_engine_loop(assets, timeframes, include_ml=False, interval_seconds=60)


if __name__ == "__main__":
    demo_start()
