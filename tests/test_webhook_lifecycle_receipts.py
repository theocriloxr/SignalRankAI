from __future__ import annotations

import asyncio
from pathlib import Path

import railway_main


def test_webhook_start_runs_post_init_before_application_start() -> None:
    source = Path("railway_main.py").read_text(encoding="utf-8")
    start = source.index("async def _start_telegram_bot")
    end = source.index("async def _stop_telegram_bot", start)
    block = source[start:end]

    assert block.index("await app_obj.initialize()") < block.index("await post_init(app_obj)")
    assert block.index("await post_init(app_obj)") < block.index("await app_obj.start()")


def test_webhook_stop_runs_post_stop_and_shutdown(monkeypatch) -> None:
    events: list[str] = []

    class App:
        updater = None

        async def stop(self):
            events.append("stop")

        async def post_stop(self, _app):
            events.append("post_stop")

        async def shutdown(self):
            events.append("shutdown")

    monkeypatch.delenv("TELEGRAM_USE_WEBHOOK", raising=False)
    asyncio.run(railway_main._stop_telegram_bot(App()))

    assert events == ["stop", "post_stop", "shutdown"]


def test_receipt_reconciler_uses_bounded_interactive_lane() -> None:
    source = Path("delivery/worker.py").read_text(encoding="utf-8")

    assert "priority=DBPriority.INTERACTIVE" in source
    assert 'label="delivery_receipt_reconcile"' in source
    assert "DELIVERY_RECONCILE_DB_TIMEOUT_SECONDS" in source
