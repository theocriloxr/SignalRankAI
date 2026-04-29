"""
Redis caching layer for high-frequency data.
Reduces API calls 90%+ while keeping data fresh.
"""
import json
import time
from typing import Optional, Dict, Any, List, Union
from datetime import timedelta
import hashlib
from core.redis_state import state

logger = logging.getLogger(__name__)

# TTLs (seconds)
CACHE_TTL = {
    'market_data_crypto': 300,    # 5 min (high vol)
    'market_data_fx': 900,        # 15 min (stable)
    'market_data_stock': 1800,    # 30 min
    'signal': 900,                # 15 min
    'user_prefs': 3600,           # 1h
    'news_sentiment': 1800,       # 30 min
}

async def cache_get(key: str) -> Optional[Dict[str, Any]]:
    """Get cached value or None."""
    try:
        cached = await state.get_sync(key)
        if cached:
            data = json.loads(cached)
            ttl_left = data.get('ttl') - time.time()
            if ttl_left > 0:
                return data.get('value')
    except Exception:
        pass
    return None

async def cache_set(key: str, value: Any, ttl_category: str = 'default') -> None:
    """Cache value with TTL."""
    try:
        ttl = CACHE_TTL.get(ttl_category, 300)
        expires = time.time() + ttl
        data = {
            'value': value,
            'ttl': expires,
            'set_at': time.time(),
        }
        await state.set_sync(key, json.dumps(data), ex=ttl)
    except Exception:
        pass

def cache_key(prefix: str, *args: Any, **kwargs: Any) -> str:
    """Deterministic cache key generator."""
    parts = [prefix]
    for arg in args:
        parts.append(str(arg)[:50])
    for k, v in sorted(kwargs.items()):
        parts.append(f"{k}:{str(v)[:50]}")
    key_str = "_".join(parts)
    return f"cache:{hashlib.md5(key_str.encode()).hexdigest()}"

async def cached_market_data(symbol: str, timeframe: str, category: str = 'market_data_crypto') -> Optional[Dict]:
    """Cached market data fetch."""
    key = cache_key('market', symbol, timeframe)
    data = await cache_get(key)
    if data:
        logger.debug(f"CACHE HIT market {symbol}:{timeframe}")
        return data
    return None

async def cache_market_data(symbol: str, timeframe: str, data: Dict, category: str = 'market_data_crypto') -> None:
    """Cache fresh market data."""
    key = cache_key('market', symbol, timeframe)
    await cache_set(key, data, ttl_category=category)

async def cached_signal(signal_id: str) -> Optional[Dict]:
    """Cached signal lookup."""
    key = cache_key('signal', signal_id)
    return await cache_get(key)

async def cache_signal(signal: Dict) -> None:
    """Cache signal."""
    key = cache_key('signal', signal.get('signal_id'))
    await cache_set(key, signal, 'signal')

async def cached_user_prefs(user_id: int) -> Dict[str, Any]:
    """Cached user preferences."""
    key = cache_key('prefs', user_id)
    prefs = await cache_get(key)
    return prefs or {}

async def cache_user_prefs(user_id: int, prefs: Dict[str, Any]) -> None:
    """Cache user preferences."""
    key = cache_key('prefs', user_id)
    await cache_set(key, prefs, 'user_prefs')

async def cached_news_sentiment(symbol: str) -> Optional[float]:
    """Cached news sentiment score."""
    key = cache_key('sentiment', symbol)
    data = await cache_get(key)
    return data.get('score') if data else None

async def cache_news_sentiment(symbol: str, score: float) -> None:
    """Cache news sentiment."""
    key = cache_key('sentiment', symbol)
    await cache_set(key, {'score': score}, 'news_sentiment')

async def cache_stats() -> Dict[str, int]:
    """Get cache statistics."""
    try:
        stats = {
            'hits': int(await state.get_sync('cache:stats:hits') or 0),
            'misses': int(await state.get_sync('cache:stats:misses') or 0),
            'evictions': int(await state.get_sync('cache:stats:evictions') or 0),
        }
        hit_rate = stats['hits'] / max(1, stats['hits'] + stats['misses']) * 100
        stats['hit_rate'] = round(hit_rate, 1)
        return stats
    except Exception:
        return {'hits': 0, 'misses': 0, 'hit_rate': 0.0}

async def record_cache_hit():
    """Record cache hit."""
    try:
        await state.incr_sync('cache:stats:hits')
    except Exception:
        pass

async def record_cache_miss():
    """Record cache miss."""
    try:
        await state.incr_sync('cache:stats:misses')
    except Exception:
        pass
