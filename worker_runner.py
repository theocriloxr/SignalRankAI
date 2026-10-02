import asyncio
import logging
from railway_main import _start_worker_loop_in_background

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker_runner")

async def main():
    logger.info("Starting isolated worker runner...")
    task = _start_worker_loop_in_background()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Worker runner shutdown")

if __name__ == "__main__":
    asyncio.run(main())
