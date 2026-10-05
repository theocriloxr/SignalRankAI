import asyncio
from types import SimpleNamespace

import httpx
import pytest


class TestRailwayRedisQueue:
    async def _run(self, monkeypatch, stream):
        import railway_main

        monkeypatch.setattr(railway_main, "_bot_ready", True)
        monkeypatch.setattr(railway_main, "_bot_application", object())
        monkeypatch.setattr(railway_main, "_use_redis_webhook_queue", True)
        monkeypatch.setattr(railway_main, "_webhook_dispatch_queue", asyncio.Queue(maxsize=10))
        calls = []

        async def _enqueue(payload, max_depth=None):
            calls.append(("legacy", payload["update_id"]))
            return True

        async def _depth():
            raise AssertionError("acknowledgement must not make a second Redis round trip")

        async def _stream_enqueue(payload, *, idempotency_key):
            calls.append(("stream", payload["update_id"], idempotency_key))
            return SimpleNamespace(accepted=True, duplicate=False)

        monkeypatch.setattr(railway_main.state, "enqueue_webhook_update", _enqueue)
        monkeypatch.setattr(railway_main.state, "webhook_queue_depth", _depth)
        monkeypatch.setattr(railway_main, "_webhook_stream", SimpleNamespace(
            configured=stream, enqueue=_stream_enqueue,
        ))

        transport = httpx.ASGITransport(app=railway_main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/telegram/webhook", json={"update_id": 777, "message": {"text": "ok"}})
            assert resp.status_code == 200
            body = resp.json()
            assert body.get("ok") is True
            assert body.get("queue_backend") == ("redis_stream" if stream else "redis")
            assert "queue_size" not in body, (
                "the acknowledgement path must not add a second Redis round trip"
            )
        assert calls == ([("stream", 777, "telegram-update:777")] if stream else [("legacy", 777)])

    @pytest.mark.parametrize("stream", [False, True])
    def test_telegram_webhook_route_uses_redis_backend(self, monkeypatch, stream):
        asyncio.run(self._run(monkeypatch, stream))
