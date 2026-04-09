from core.redis_state import RedisState


class _FakeRedis:
    def __init__(self):
        self.q = []

    def llen(self, _key):
        return len(self.q)

    def rpush(self, _key, raw):
        self.q.append(raw)
        return len(self.q)

    def blpop(self, _key, timeout=0):
        if not self.q:
            return None
        return (_key, self.q.pop(0))


def test_webhook_queue_roundtrip_with_redis_client_stub():
    rs = RedisState()
    fake = _FakeRedis()
    rs._get_redis_sync = lambda: fake  # type: ignore[attr-defined]

    payload = {"update_id": 99, "message": {"text": "hi"}}

    assert rs.enqueue_webhook_update_sync(payload, max_depth=5) is True
    assert rs.webhook_queue_depth_sync() == 1

    got = rs.dequeue_webhook_update_sync(timeout_seconds=0)
    assert isinstance(got, dict)
    assert got.get("update_id") == 99
    assert rs.webhook_queue_depth_sync() == 0
