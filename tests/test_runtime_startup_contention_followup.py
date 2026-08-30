from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_redis_stream_timeout_is_an_idle_poll_not_worker_failure() -> None:
    from core.redis_streams import RecoverableStream

    client = AsyncMock()
    client.xautoclaim.return_value = ("0-0", [])
    client.xreadgroup.side_effect = TimeoutError("idle blocking read")
    stream = RecoverableStream(
        name="test:updates",
        group="test-workers",
        redis_url="redis://configured",
    )
    stream._get_client = AsyncMock(return_value=client)
    stream.ensure_group = AsyncMock(return_value=True)

    assert await stream.read(consumer="worker-1", block_ms=1_000) == []


def test_resend_lock_is_stable_and_isolated_by_railway_environment(monkeypatch) -> None:
    from signalrank_telegram.bot import _resend_advisory_lock

    monkeypatch.delenv("RESEND_JOB_LOCK_ID", raising=False)
    monkeypatch.delenv("RESEND_JOB_LOCK_SCOPE", raising=False)
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project")
    monkeypatch.setenv("RAILWAY_SERVICE_ID", "service")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "staging")
    staging_first = _resend_advisory_lock()
    staging_second = _resend_advisory_lock()

    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "production")
    production = _resend_advisory_lock()

    assert staging_first == staging_second
    assert staging_first[0] != production[0]


def test_startup_jobs_do_not_ignore_operational_guards() -> None:
    source = Path("signalrank_telegram/bot.py").read_text(encoding="utf-8")
    post_init = source[source.index("async def _post_init"):source.index("async def _post_stop")]
    free_summary = source[
        source.index("def send_free_delayed_summaries"):
        source.index("def auto_retrain_ml_model_job", source.index("def send_free_delayed_summaries"))
    ]

    assert 'if _env_bool("ACTIVE_SIGNAL_KEYBOARD_REFRESH_ENABLED", False):' in post_init
    assert 'label="bot_commands.tier_snapshot"' in post_init
    assert "resolve_user_tier" not in post_init
    assert 'priority="interactive"' in free_summary


def test_receipt_recovery_has_startup_and_operation_deadlines() -> None:
    source = Path("delivery/worker.py").read_text(encoding="utf-8")

    assert "DELIVERY_RECONCILE_STARTUP_DELAY_SECONDS" in source
    assert "asyncio.wait_for(_persist(), timeout=timeout_seconds + 1.0)" in source
    assert "delivery_receipt_reconcile_timeout" in source
