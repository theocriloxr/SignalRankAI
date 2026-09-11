from __future__ import annotations

import asyncio
import logging
import os

from db.storage_maintenance import learning_history_maintenance_loop, run_learning_history_retention_once


async def main() -> None:
    logging.basicConfig(
        level=getattr(logging, str(os.getenv("LOG_LEVEL") or "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Do one pass immediately so a redeploy can be used as an explicit
    # maintenance trigger, then remain alive for the bounded periodic loop.
    await run_learning_history_retention_once()
    await learning_history_maintenance_loop()


if __name__ == "__main__":
    asyncio.run(main())
