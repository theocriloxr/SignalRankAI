import asyncio

import httpx


class TestRailwayRedisQueue:
    async def _run(self):
        import railway_main

        railway_main._bot_ready = True
        railway_main._bot_application = object()
        railway_main._use_redis_webhook_queue = True
        railway_main._webhook_dispatch_queue = asyncio.Queue(maxsize=10)

        async def _enqueue(payload, max_depth=None):
            return True

        async def _depth():
            return 3

        railway_main.state.enqueue_webhook_update = _enqueue  # type: ignore[attr-defined]
        railway_main.state.webhook_queue_depth = _depth  # type: ignore[attr-defined]

        transport = httpx.ASGITransport(app=railway_main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/telegram/webhook", json={"update_id": 777, "message": {"text": "ok"}})
            assert resp.status_code == 200
            body = resp.json()
            assert body.get("ok") is True
            assert body.get("queue_backend") == "redis"
            assert int(body.get("queue_size", 0)) == 3

    def test_telegram_webhook_route_uses_redis_backend(self):
        asyncio.run(self._run())
