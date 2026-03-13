# Script to purge all signals for UNIUSDT, APTUSDT, POLUSDT from the database
import asyncio
from utils.async_runner import run_sync
from db.session import async_session
from db.models import Signal
from sqlalchemy import delete

EXCLUDED_ASSETS = ["UNIUSDT", "APTUSDT", "POLUSDT"]

async def purge_signals():
    async with async_session() as session:
        for asset in EXCLUDED_ASSETS:
            await session.execute(delete(Signal).where(Signal.asset == asset))
        await session.commit()
    print(f"Purged all signals for: {', '.join(EXCLUDED_ASSETS)}")

if __name__ == "__main__":
    run_sync(purge_signals())
