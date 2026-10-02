import asyncio
import logging
import os
from railway_main import _start_engine_loop_in_background

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("engine_runner")

async def main():
    logger.info("Starting isolated engine runner...")
    # Add proper engine init here
    task = _start_engine_loop_in_background()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Engine runner shutdown")

if __name__ == "__main__":
    asyncio.run(main())
