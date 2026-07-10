import pytest


@pytest.mark.asyncio
async def test_noncritical_session_drops_while_critical_active(monkeypatch):
    import db.session as dbs

    monkeypatch.setenv("DB_NONCRITICAL_WRITE_DROP_ON_GATE_TIMEOUT", "1")
    monkeypatch.setenv("DB_NONCRITICAL_DROP_WHEN_CRITICAL_ACTIVE", "1")

    dbs._mark_critical_db_start()
    try:
        with pytest.raises(dbs.NoncriticalWriteDropped):
            async with dbs.get_session(noncritical=True):
                pass
    finally:
        dbs._mark_critical_db_end()


def test_worker_shadow_tracker_env_alias(monkeypatch):
    import worker.worker as worker

    monkeypatch.setenv("SHADOW_OUTCOME_TRACKER_ENABLED", "0")
    monkeypatch.delenv("WORKER_SHADOW_TRACKER_ENABLED", raising=False)
    assert worker._env_bool_any(("SHADOW_OUTCOME_TRACKER_ENABLED", "WORKER_SHADOW_TRACKER_ENABLED"), True) is False

    monkeypatch.setenv("SHADOW_OUTCOME_TRACKER_ENABLED", "1")
    assert worker._env_bool_any(("SHADOW_OUTCOME_TRACKER_ENABLED", "WORKER_SHADOW_TRACKER_ENABLED"), False) is True


def test_signal_store_timeout_env_is_used(monkeypatch):
    import os
    from pathlib import Path

    monkeypatch.setenv("SIGNAL_STORE_TIMEOUT_SECONDS", "45")
    text = Path("db/pg_compat.py").read_text()
    assert "SIGNAL_STORE_TIMEOUT_SECONDS" in text
    assert "get_session(critical=True)" in text
    assert float(os.getenv("SIGNAL_STORE_TIMEOUT_SECONDS")) == 45.0


def test_bot_background_flags_present():
    from pathlib import Path

    text = Path("signalrank_telegram/bot.py").read_text()
    assert "SEND_OUTCOME_NOTIFICATIONS_ENABLED" in text
    assert "FREE_RANDOM_DISTRIBUTION_ENABLED" in text
    assert "RESEND_SKIP_WHEN_CRITICAL_DB_ACTIVE" in text
    assert "OUTCOME_NOTIFICATION_STARTUP_DELAY_SECONDS" in text
    assert "FREE_DISTRIBUTION_STARTUP_DELAY_SECONDS" in text
