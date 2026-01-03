import asyncio

from config import OWNER_IDS
from core.redis_state import state

try:
    from db.access import resolve_user_tier as _resolve_user_tier_pg
    from db.session import ENGINE as _PG_ENGINE
except Exception:  # pragma: no cover
    _resolve_user_tier_pg = None
    _PG_ENGINE = None

def resolve_user_tier(user_id):
    """Resolve user tier with priority: OWNER > ADMIN (temp) > DB tier > FREE.
    
    Tier Resolution Order:
    1. Check OWNER_IDS config (highest priority - env variables)
    2. Check temp ADMIN access via /unlock command
    3. Query Postgres for user's actual tier
    4. Default to FREE if all lookups fail
    
    IMPORTANT: If user is in OWNER_IDS, they are ALWAYS OWNER,
    regardless of database tier. This prevents FREE DB tiers from overriding.
    
    Returns: OWNER|ADMIN|VIP|PREMIUM|FREE (uppercase)
    """
    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        return "FREE"
    
    # PRIORITY 1: Check OWNER_IDS (environment variable - highest priority)
    # This ensures owner is never marked as FREE from database
    if user_id_int in OWNER_IDS:
        return "OWNER"

    # PRIORITY 2: Check temporary ADMIN access via /unlock command
    # (This is invalidated automatically when BYPASS_KEY rotates)
    try:
        if state.has_temp_owner_sync(user_id_int):
            return "ADMIN"
    except Exception:
        pass

    # PRIORITY 3: Query Postgres for user's tier (fallback)
    if _PG_ENGINE is None or _resolve_user_tier_pg is None:
        # If Postgres not available, return FREE
        return "FREE"

    try:
        # PTB sync handlers commonly run in a worker thread; asyncio.run is safe there.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop - safe to use asyncio.run
            tier = asyncio.run(_resolve_user_tier_pg(user_id_int))
            return (tier or "FREE").strip().upper()
    except Exception:
        pass

    # FALLBACK: Default to FREE if lookup fails
    return "FREE"