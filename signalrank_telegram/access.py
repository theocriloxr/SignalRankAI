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
    """Postgres-only tier resolution. Returns OWNER/VIP/PREMIUM/FREE."""
    if user_id in OWNER_IDS:
        return "OWNER"

    # If a user was granted temporary owner access via /unlock,
    # treat them as ADMIN (this is invalidated automatically when BYPASS_KEY rotates).
    try:
        if state.has_temp_owner_sync(int(user_id)):
            return "ADMIN"
    except Exception:
        pass

    # Postgres required
    if _PG_ENGINE is None or _resolve_user_tier_pg is None:
        raise RuntimeError("DATABASE_URL not configured. Postgres is required.")

    try:
        # PTB sync handlers commonly run in a worker thread; asyncio.run is safe there.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            tier = asyncio.run(_resolve_user_tier_pg(int(user_id)))
            return (tier or "free").strip().upper()
    except Exception:
        pass

    # Default to FREE if lookup fails
    return "FREE"