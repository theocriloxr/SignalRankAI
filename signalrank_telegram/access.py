import asyncio

from config import OWNER_IDS
from db.database import get_subscription

try:
    from db.access import resolve_user_tier as _resolve_user_tier_pg
    from db.session import ENGINE as _PG_ENGINE
except Exception:  # pragma: no cover
    _resolve_user_tier_pg = None
    _PG_ENGINE = None

def resolve_user_tier(user_id):
    if user_id in OWNER_IDS:
        return "OWNER"

    # Prefer Postgres when configured.
    try:
        if _PG_ENGINE is not None and _resolve_user_tier_pg is not None:
            # PTB sync handlers commonly run in a worker thread; asyncio.run is safe there.
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                tier = asyncio.run(_resolve_user_tier_pg(int(user_id)))
                return (tier or "free").strip().upper()
    except Exception:
        pass

    # Legacy SQLite fallback.
    sub = get_subscription(user_id)
    if sub is None or sub.get('expired', True):
        return "FREE"
    if sub.get('bypass_key_used'):
        return "OWNER"
    return (sub.get('tier', 'FREE') or 'FREE')