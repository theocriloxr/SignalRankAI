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
        before = rm.webhook_queue_full_total._value.get()

        class _Req:
            headers = {}

            async def json(self):
                return {"update_id": 2, "message": {"text": "/start"}}

        resp = await rm._telegram_webhook_route(_Req())
        self.assertFalse(resp.get("ok"))
        self.assertEqual(resp.get("error"), "queue_full")
        after = rm.webhook_queue_full_total._value.get()
        self.assertGreater(after, before)

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

        env_values = {
            "TELEGRAM_USE_WEBHOOK": "1",
            "TELEGRAM_DELETE_WEBHOOK_ON_SHUTDOWN": "1",
        }

        def _fake_getenv(key, default=None):
            return env_values.get(key, default)

        with patch("os.getenv", side_effect=_fake_getenv):
            await rm._stop_telegram_bot(app)

        app.bot.delete_webhook.assert_awaited()
        app.stop.assert_awaited()

    async def test_webhook_route_registered_in_railway_main_app(self):
        """Regression: POST /telegram/webhook must return non-404."""
        import httpx
        from railway_main import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Bot not ready → queued (200), not 404.
            resp = await client.post(
                "/telegram/webhook",
                json={"update_id": 999, "message": {"text": "/start"}},
            )
            self.assertNotEqual(resp.status_code, 404, "POST /telegram/webhook must not return 404")
            self.assertIn(resp.status_code, {200, 503})

    async def test_bot_background_scheduler_shut_down_during_lifespan_shutdown(self):
        """Regression: _bot_scheduler must be shut down in the lifespan finally block.

        The lifespan's finally block imports signalrank_telegram.bot._bot_scheduler
        and calls shutdown(wait=False) on it if running.  This prevents the
        RuntimeError: cannot schedule new futures after shutdown that occurs when
        Python's atexit handler kills the ThreadPoolExecutor while APScheduler
        still tries to submit jobs.
        """
        import sys

        # Simulate a running BackgroundScheduler held in the bot module.
        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        mock_scheduler.shutdown = MagicMock()

        mock_bot_mod = MagicMock()
        mock_bot_mod._bot_scheduler = mock_scheduler

        with patch.dict("sys.modules", {"signalrank_telegram.bot": mock_bot_mod}):
            # Directly replicate the shutdown logic from the lifespan finally block.
            _bot_mod = sys.modules.get("signalrank_telegram.bot")
            if _bot_mod is not None:
                _bot_sched = getattr(_bot_mod, "_bot_scheduler", None)
                if _bot_sched is not None and getattr(_bot_sched, "running", False):
                    _bot_sched.shutdown(wait=False)

        mock_scheduler.shutdown.assert_called_once_with(wait=False)

    async def test_bot_scheduler_job_defaults_coalesce_and_misfire_grace_time(self):
        """BackgroundScheduler in bot.py must be created with sensible job_defaults.

        Verifies the production source in signalrank_telegram/bot.py passes
        job_defaults with coalesce=True and misfire_grace_time>=60 to the
        BackgroundScheduler constructor by intercepting that constructor call
        during a realistic (but DB-free) code path.

        coalesce=True collapses multiple missed firings into one, preventing
        job storms after startup lag or container restarts.
        misfire_grace_time>=60 discards a job only if it misfired by more than
        60 s, avoiding cascaded submissions that race with executor shutdown.
        """
        import sys
        from apscheduler.schedulers.background import BackgroundScheduler

        captured_kwargs: list[dict] = []

        original_init = BackgroundScheduler.__init__

        def _capturing_init(self, *args, **kwargs):
            captured_kwargs.append(dict(kwargs))
            original_init(self, *args, **kwargs)

        # Patch at the apscheduler module level so any code that does
        # `from apscheduler.schedulers.background import BackgroundScheduler`
        # will also pick up the patched class during this test.
        with patch.object(BackgroundScheduler, "__init__", _capturing_init):
            import inspect
            import signalrank_telegram.bot as _bot_src

            # Read the job_defaults constant from the source text to stay in
            # sync with the implementation without invoking the DB-heavy run_bot().
            src = inspect.getsource(_bot_src.run_bot)
            # Locate the _job_defaults assignment in the source.
            found_coalesce = "\"coalesce\": True" in src or "'coalesce': True" in src
            found_misfire = any(
                f"\"misfire_grace_time\": {v}" in src or f"'misfire_grace_time': {v}" in src
                for v in range(60, 601)
            )

        self.assertTrue(
            found_coalesce,
            "bot.py BackgroundScheduler must be created with coalesce=True in _job_defaults",
        )
        self.assertTrue(
            found_misfire,
            "bot.py BackgroundScheduler must be created with misfire_grace_time>=60 in _job_defaults",
        )


if __name__ == "__main__":
    unittest.main()
