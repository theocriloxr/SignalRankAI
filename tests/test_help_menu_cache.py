from signalrank_telegram.command_access import get_help_message
import signalrank_telegram.command_access as ca


def test_get_help_message_uses_cache(monkeypatch):
    cache = {}
    set_calls = {"count": 0}

    monkeypatch.setenv("DASHBOARD_URL", "")

    monkeypatch.setattr(ca.state, "cache_get_sync", lambda k: cache.get(k))

    def _cache_set(k, v, ex=None):
        set_calls["count"] += 1
        cache[k] = v

    monkeypatch.setattr(ca.state, "cache_set_sync", _cache_set)

    m1 = get_help_message("free")
    m2 = get_help_message("free")

    assert "FREE" in m1.upper()
    assert m1 == m2
    assert set_calls["count"] == 1
