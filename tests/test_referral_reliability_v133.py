from __future__ import annotations

from pathlib import Path


def _railway_env(monkeypatch) -> None:
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", "SignalRankAI")
    monkeypatch.setenv("RUN_MODE", "all")
    monkeypatch.setenv("DB_ROLE", "all")
    monkeypatch.setenv("PUBLIC_TESTING_MODE", "0")
    monkeypatch.setenv("DB_USE_NULLPOOL", "0")
    monkeypatch.setenv("DB_POOL_SIZE", "12")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "6")
    monkeypatch.setenv("DB_POOL_RAILWAY_ABSOLUTE_CAP", "12")
    monkeypatch.setenv("DB_MAX_OVERFLOW_RAILWAY_ABSOLUTE_CAP", "6")


def test_monolith_pool_remains_safe_without_review_flag(monkeypatch) -> None:
    from db import session as db_session

    _railway_env(monkeypatch)
    monkeypatch.delenv("DB_ALLOW_REVIEWED_MONOLITH_POOL", raising=False)
    assert db_session._effective_pool_settings() == (2, 0)


def test_reviewed_monolith_pool_is_bounded(monkeypatch) -> None:
    from db import session as db_session

    _railway_env(monkeypatch)
    monkeypatch.setenv("DB_ALLOW_REVIEWED_MONOLITH_POOL", "1")
    monkeypatch.setenv("DB_REVIEWED_MONOLITH_POOL_MAX", "8")
    monkeypatch.setenv("DB_REVIEWED_MONOLITH_OVERFLOW_MAX", "2")
    assert db_session._effective_pool_settings() == (8, 2)


def test_public_testing_blocks_reviewed_monolith_pool(monkeypatch) -> None:
    from db import session as db_session

    _railway_env(monkeypatch)
    monkeypatch.setenv("PUBLIC_TESTING_MODE", "1")
    monkeypatch.setenv("DB_ALLOW_REVIEWED_MONOLITH_POOL", "1")
    assert db_session._effective_pool_settings() == (2, 0)


def test_referral_commands_never_emit_unstored_fallback_codes() -> None:
    source = Path("signalrank_telegram/commands.py").read_text(encoding="utf-8")
    assert "hashlib.sha1(str(user_id)" not in source
    assert 'referral_code = str(user_id)' not in source
    assert "No temporary or invalid code was created" in source
    assert 'label="referral.invite"' in source
    assert 'label="referral.dashboard"' in source


def test_referral_progress_is_lifetime_based_and_no_nested_tier_session() -> None:
    source = Path("db/pg_features.py").read_text(encoding="utf-8")
    referral_section = source[source.index("async def get_or_create_referral_code"):source.index("# === NEW: Signal Archiving")]
    assert "referrer_user.referral_count = 0" not in referral_section
    assert "from db.access import resolve_user_tier" not in referral_section
    assert 'reward_ref = f"REFERRAL:{referrer_tid}:{batch_number}"' in referral_section
    assert "needed = int(requirement if toward_next == 0" in referral_section
    assert "record_referral_conversion" in referral_section


def test_referral_migration_follows_current_head() -> None:
    source = Path("db/migrations/versions/0032_referral_reliability.py").read_text(encoding="utf-8")
    assert 'revision = "0032_referral_reliability"' in source
    assert 'down_revision = "0031_perf_paper_reliability"' in source
    assert "uq_referral_rewards_reference" in source


def test_successful_webhook_processing_does_not_retry_when_xack_returns_zero() -> None:
    source = Path("railway_main.py").read_text(encoding="utf-8")
    assert "stream acknowledgement failed" not in source
    assert "stream ack returned zero after successful processing" in source


def test_startup_command_scope_refresh_is_not_an_unbounded_user_scan() -> None:
    source = Path("signalrank_telegram/bot.py").read_text(encoding="utf-8")
    assert 'BOT_COMMAND_SCOPE_BULK_REFRESH_ENABLED", "0"' in source
    assert ".limit(bulk_limit)" in source
    assert "using global FREE plus owner/admin scopes" in source
