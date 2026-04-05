import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


class TestRailwayLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_webhook_route_queues_when_bot_not_ready(self):
        import railway_main as rm

        rm._bot_ready = False
        rm._bot_application = None
        rm._pending_webhook_updates.clear()

        class _Req:
            headers = {}

            async def json(self):
                return {"update_id": 123, "message": {"text": "/start"}}

        resp = await rm._telegram_webhook_route(_Req())
        self.assertTrue(resp.get("ok"))
        self.assertTrue(resp.get("queued"))
        self.assertEqual(len(rm._pending_webhook_updates), 1)

    async def test_webhook_route_returns_queue_full(self):
        import railway_main as rm

        rm._bot_ready = True
        rm._bot_application = object()
        rm._webhook_dispatch_queue = asyncio.Queue(maxsize=1)
        rm._webhook_dispatch_queue.put_nowait({"update_id": 1})

        class _Req:
            headers = {}

            async def json(self):
                return {"update_id": 2, "message": {"text": "/start"}}

        resp = await rm._telegram_webhook_route(_Req())
        self.assertFalse(resp.get("ok"))
        self.assertEqual(resp.get("error"), "queue_full")

    async def test_build_scheduler_registers_expected_jobs(self):
        import railway_main as rm

        scheduler = rm._build_scheduler()
        job_ids = {job.id for job in scheduler.get_jobs()}
        self.assertIn("wl_capacity", job_ids)
        self.assertIn("wl_monitor", job_ids)
        self.assertIn("ml_archive_backfill", job_ids)

    async def test_stop_telegram_bot_deletes_webhook_when_enabled(self):
        import railway_main as rm

        app = MagicMock()
        app.bot = MagicMock()
        app.bot.delete_webhook = AsyncMock()
        app.stop = AsyncMock()
        app.updater = MagicMock()
        app.updater.stop = AsyncMock()

        with patch("os.getenv", side_effect=lambda k, d=None: "1" if k in {"TELEGRAM_USE_WEBHOOK", "TELEGRAM_DELETE_WEBHOOK_ON_SHUTDOWN"} else d):
            await rm._stop_telegram_bot(app)

        app.bot.delete_webhook.assert_awaited()
        app.stop.assert_awaited()


if __name__ == "__main__":
    unittest.main()
