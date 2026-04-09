import asyncio

import signalrank_telegram.access as access


def test_resolve_user_tier_uses_cache(monkeypatch):
    cache = {}
    db_calls = {"count": 0}

    async def fake_resolve_user_tier_pg(user_id: int):
        db_calls["count"] += 1
        await asyncio.sleep(0)
        return "premium"

    monkeypatch.setattr(access, "OWNER_IDS", set())
    monkeypatch.setattr(access, "ADMIN_IDS", set())
    monkeypatch.setattr(access, "_resolve_user_tier_pg", fake_resolve_user_tier_pg)

    monkeypatch.setattr(access.state, "has_temp_owner_sync", lambda _uid: False)
    monkeypatch.setattr(access.state, "cache_get_sync", lambda k: cache.get(k))

    def _cache_set(k, v, ex=None):
        cache[k] = v

    monkeypatch.setattr(access.state, "cache_set_sync", _cache_set)

    t1 = access.resolve_user_tier(123456)
    t2 = access.resolve_user_tier(123456)

    assert t1 == "PREMIUM"
    assert t2 == "PREMIUM"
    assert db_calls["count"] == 1
