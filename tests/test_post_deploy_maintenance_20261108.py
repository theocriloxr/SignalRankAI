"""Post-deploy maintenance (8 Nov 2026): ledger refresh after audited corrections and the one-off
stale-tick label correction, both run by analytics instead of an owner shell step."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from services import post_deploy_maintenance as pdm

ROOT = Path(__file__).resolve().parents[1]
_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")


class _State:
    def __init__(self):
        self.data = {}

    def get_sync(self, key):
        return self.data.get(key)

    def set_sync(self, key, value, ex=None):
        self.data[key] = value


def test_owner_command_is_registered_and_apply_needs_a_dry_run():
    owner = (ROOT / "signalrank_telegram" / "owner_commands.py").read_text(encoding="utf-8")
    bot = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    assert 'CommandHandler("stale_tick_relabel"' in bot
    assert 'if action == "apply" and not preview:' in owner and "_is_strict_owner" in owner


def test_relabel_window_ends_at_the_stale_tick_fix_not_today():
    assert pdm.RELABEL_UNTIL.isoformat() == "2026-11-04T08:00:00"
    source = (ROOT / "runtime" / "analytics.py").read_text(encoding="utf-8")
    assert 'name="post-deploy-maintenance"' in source


def test_disabled_by_switch(monkeypatch):
    calls = []
    monkeypatch.setenv("POST_DEPLOY_MAINTENANCE_DELAY_SECONDS", "0")
    monkeypatch.setenv("POST_DEPLOY_LEDGER_REFRESH", "0")
    monkeypatch.setenv("POST_DEPLOY_STALE_TICK_RELABEL", "0")

    async def boom():
        calls.append(1)

    monkeypatch.setattr(pdm, "refresh_ledgers_for_corrected_outcomes", boom)
    monkeypatch.setattr(pdm, "stale_tick_relabel_preview_once", boom)
    asyncio.run(pdm._run_maintenance(asyncio.Event()))
    assert calls == []


def test_task_stays_alive_after_its_work_until_stop(monkeypatch):
    """9 Nov 2026: analytics treats a supervised task that returns as a crash and restarts the
    service. The one-shot maintenance returned after ~2 min, so analytics restarted 260 times in
    10 h (``analytics_task_stopped_unexpectedly:post-deploy-maintenance``)."""
    calls = []
    monkeypatch.setenv("POST_DEPLOY_MAINTENANCE_DELAY_SECONDS", "0")

    async def work():
        calls.append("work")

    monkeypatch.setattr(pdm, "refresh_ledgers_for_corrected_outcomes", work)
    monkeypatch.setattr(pdm, "stale_tick_relabel_preview_once", work)

    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(pdm.post_deploy_maintenance(stop))
        await asyncio.sleep(0.2)
        assert calls == ["work", "work"]
        assert not task.done()  # finished its work but must not look like a stopped task
        stop.set()
        await asyncio.wait_for(task, timeout=1)

    asyncio.run(scenario())


def test_task_survives_failing_work(monkeypatch):
    monkeypatch.setenv("POST_DEPLOY_MAINTENANCE_DELAY_SECONDS", "0")

    async def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(pdm, "refresh_ledgers_for_corrected_outcomes", boom)
    monkeypatch.setattr(pdm, "stale_tick_relabel_preview_once", boom)

    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(pdm.post_deploy_maintenance(stop))
        await asyncio.sleep(0.2)
        assert not task.done()
        stop.set()
        await asyncio.wait_for(task, timeout=1)

    asyncio.run(scenario())


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_runs_on_postgres_and_relabels_once(monkeypatch):
    from core import redis_state
    from db.session import _normalize_database_url

    url = _normalize_database_url(_PG_DSN, async_driver=True)
    monkeypatch.setenv("DATABASE_URL", url)
    fake = _State()
    monkeypatch.setattr(redis_state, "state", fake)

    async def scenario():
        from db.session import dispose_engine_for_event_loop

        try:
            assert await pdm.refresh_ledgers_for_corrected_outcomes() == 0  # query valid; nothing corrected here
            first = await pdm.stale_tick_relabel_preview_once()
            assert first["mode"] == "dry_run" and pdm.PREVIEW_KEY in fake.data
            assert pdm.RELABEL_MARKER not in fake.data  # applying is the owner's call
            assert await pdm.stale_tick_relabel_preview_once() == {"skipped": "already_previewed"}
            applied = await pdm.run_stale_tick_relabel(apply=True)
            assert applied["mode"] == "apply" and pdm.RELABEL_MARKER in fake.data
        finally:
            await dispose_engine_for_event_loop()

    asyncio.run(scenario())
