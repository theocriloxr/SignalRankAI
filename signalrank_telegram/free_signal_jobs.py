"""
CRITICAL FIX: Free Signal Queue Distribution Job

This job is already defined in bot.py but was NOT registered with APScheduler.
This causes FREE users to never receive signals from the global pool.

Solution: Add to signal_distribution.py and import in bot.py scheduler setup.
"""

import logging
from datetime import datetime, timedelta, timezone
from utils.timeutils import now_utc_naive
from utils.async_runner import run_sync

logger = logging.getLogger(__name__)


def distribute_random_signals_to_free_users_job():
    """
    APScheduler job: distribute random signals to FREE users from global pool.
    
    This runs periodically to give FREE users signals from the global pool.
    The signals are randomly selected and distributed within daily limits.
    
    Runs every 30 minutes by default.
    """
    logger.info("🎲 Starting FREE signal distribution job...")
    
    try:
        from db.session import get_session
        from db.pg_features import queue_random_free_signals_for_all_users
        
        async def _do_distribute():
            async with get_session() as session:
                count = await queue_random_free_signals_for_all_users(session)
                if count > 0:
                    logger.info(f"📬 Queued signals for {count} FREE user(s)")
                    await session.commit()
                else:
                    logger.info("✅ All FREE users have reached daily limit or no new signals")
        
        run_sync(_do_distribute())
        logger.info("✅ FREE signal distribution job completed")
        
    except Exception as e:
        logger.error(f"❌ FREE signal distribution job failed: {e}")


# Alias for backward compatibility
def free_distribution_job():
    """Alias for distribute_random_signals_to_free_users_job"""
    return distribute_random_signals_to_free_users_job()


# Import for the job to be called by scheduler
# Add this to bot.py scheduler setup:
#
# scheduler.add_job(
#     distribute_random_signals_to_free_users_job,
#     "interval",
#     minutes=30,
#     id="free_signal_distribution",
#     replace_existing=True,
# )
