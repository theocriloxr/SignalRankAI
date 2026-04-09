import asyncio
from utils.async_runner import run_sync
import os

from config import OWNER_IDS, ADMIN_IDS
from core.redis_state import state

try:
    from db.access import resolve_user_tier as _resolve_user_tier_pg
    # ENGINE import removed; use get_engine_for_event_loop() if needed
except Exception:  # pragma: no cover
    _resolve_user_tier_pg = None


def _tier_cache_key(user_id: int) -> str:
    return f"user_tier:{int(user_id)}"


def _tier_cache_ttl_seconds() -> int:
    try:
        return max(15, int((os.getenv("USER_TIER_CACHE_TTL_SECONDS") or "60").strip()))
    except Exception:
        return 60

def resolve_user_tier(user_id):
    """Resolve user tier with priority: OWNER > ADMIN(config) > ADMIN(temp) > DB tier > FREE.
    
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
        try:
            state.cache_set_sync(_tier_cache_key(user_id_int), "OWNER", ex=_tier_cache_ttl_seconds())
        except Exception:
            pass
        return "OWNER"

    # PRIORITY 2: Check configured ADMIN_IDS from environment
    if user_id_int in ADMIN_IDS:
        try:
            state.cache_set_sync(_tier_cache_key(user_id_int), "ADMIN", ex=_tier_cache_ttl_seconds())
        except Exception:
            pass
        return "ADMIN"

    # Cache fast-path
    try:
        cached = str(state.cache_get_sync(_tier_cache_key(user_id_int)) or "").strip().upper()
        if cached in {"FREE", "PREMIUM", "VIP", "ADMIN", "OWNER"}:
            return cached
    except Exception:
        pass

    # PRIORITY 3: Check temporary ADMIN access via /unlock command
    # (This is invalidated automatically when BYPASS_KEY rotates)
    try:
        if state.has_temp_owner_sync(user_id_int):
            try:
                state.cache_set_sync(_tier_cache_key(user_id_int), "ADMIN", ex=_tier_cache_ttl_seconds())
            except Exception:
                pass
            return "ADMIN"
    except Exception:
        pass

    # PRIORITY 4: Query Postgres for user's tier (fallback)
    if _resolve_user_tier_pg is None:
        # If Postgres not available, return FREE
        try:
            state.cache_set_sync(_tier_cache_key(user_id_int), "FREE", ex=_tier_cache_ttl_seconds())
        except Exception:
            pass
        return "FREE"

    try:
        tier = run_sync(_resolve_user_tier_pg(user_id_int))
        resolved = (tier or "FREE").strip().upper()
        try:
            state.cache_set_sync(_tier_cache_key(user_id_int), resolved, ex=_tier_cache_ttl_seconds())
        except Exception:
            pass
        return resolved
    except Exception:
        pass

    # FALLBACK: Default to FREE if lookup fails
    try:
        state.cache_set_sync(_tier_cache_key(user_id_int), "FREE", ex=_tier_cache_ttl_seconds())
    except Exception:
        pass
    return "FREE"