import unittest

import httpx


class TestNoRedisRuntimeState(unittest.TestCase):
    def test_rate_limit_fallback_works_without_pg_or_redis(self):
        from core.redis_state import RedisState

        rs = RedisState()
        rs._pg_available = lambda: False  # type: ignore[attr-defined]

        uid = 999001
        self.assertFalse(rs.rate_limited_sync(uid, limit=2, window_seconds=60))
        self.assertFalse(rs.rate_limited_sync(uid, limit=2, window_seconds=60))
        self.assertTrue(rs.rate_limited_sync(uid, limit=2, window_seconds=60))

    def test_killswitch_fallback_memory_roundtrip(self):
        from core.redis_state import RedisState

        rs = RedisState()
        rs._pg_available = lambda: False  # type: ignore[attr-defined]

        rs.set_killswitch_sync(True, "maintenance")
        ks = rs.get_killswitch_sync()
        self.assertTrue(ks.enabled)
        self.assertEqual(ks.reason, "maintenance")


class TestRailwayWebhookNoRedis(unittest.IsolatedAsyncioTestCase):
    async def test_webhook_queues_updates_while_bot_initializes(self):
        import railway_main

        railway_main._pending_webhook_updates.clear()
        railway_main._bot_ready = False
        railway_main._bot_application = None

        transport = httpx.ASGITransport(app=railway_main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/telegram/webhook", json={"update_id": 1001, "message": {"text": "hi"}})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data.get("queued"))
            self.assertFalse(data.get("bot_ready"))

            status = await client.get("/telegram/webhook_status")
            self.assertEqual(status.status_code, 200)
            body = status.json()
            self.assertTrue(body.get("ok"))
            self.assertFalse(body.get("bot_ready"))
            self.assertGreaterEqual(int(body.get("queued_updates", 0)), 1)


if __name__ == "__main__":
    unittest.main()
