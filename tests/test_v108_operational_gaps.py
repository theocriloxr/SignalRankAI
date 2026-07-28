from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v108_is_default_version() -> None:
    assert 'default="1.1.0"' in _source("core/version.py")


def test_resend_obeys_delivery_allowlist_and_prefilters_queue_staleness() -> None:
    source = _source("signalrank_telegram/bot.py")
    assert 'DELIVERY_AUDIENCE_ALLOWLIST' in source
    assert 'RESEND_AUDIENCE_ALLOWLIST_ONLY' in source
    assert 'RESEND_MAX_USERS_PER_RUN' in source
    assert 'evaluate_time_to_telegraph' in source
    assert '[resend] skipped queue-stale signal=' in source
    assert 'get_signal_outcome_status(signal_id)' not in source
    assert 'terminal_signal_ids' in source


def test_monitor_refresh_releases_db_before_network_io() -> None:
    source = _source("signalrank_telegram/bot.py")
    start = source.index("    def refresh_monitor_snapshots_job():")
    end = source.index("    def ml_market_analysis_job():", start)
    job = source[start:end]
    assert 'label="monitor_refresh.snapshot"' in job
    assert 'label="monitor_refresh.persist"' in job
    assert 'MONITOR_REFRESH_JOB_TIMEOUT_SECONDS' in job
    assert 'asyncio.Semaphore(concurrency)' in job
    # Snapshot DB context closes before the Telegram Bot is created.
    assert job.index('label="monitor_refresh.snapshot"') < job.index('bot = Bot(')
    assert job.index('bot = Bot(') < job.index('label="monitor_refresh.persist"')


def test_rich_messages_require_explicit_runtime_certification() -> None:
    rich = _source("signalrank_telegram/rich_messages.py")
    bot = _source("signalrank_telegram/bot.py")
    assert 'TELEGRAM_RICH_MESSAGES_CERTIFIED' in rich
    assert 'return bool(enabled and certified)' in rich
    assert 'rich_messages_enabled()' in bot


def test_execution_copy_is_signal_specific_and_broker_error_is_friendly() -> None:
    formatter = _source("signalrank_telegram/tier_signal_formatter.py")
    bot = _source("signalrank_telegram/bot.py")
    assert 'broker_account_ready' in formatter
    assert 'execution_ready' in formatter
    assert 'AUTO_TRADE_ENABLED' not in formatter[formatter.index("def _execution_mode"):formatter.index("def _tp_notes_for_execution", formatter.index("def _execution_mode"))]
    assert 'Your broker account is not connected and verified yet' in bot
    assert 'Reference: <code>{reason_key[:80]}' in bot


def test_signal_command_uses_canonical_freshness_policy() -> None:
    commands = _source("signalrank_telegram/commands.py")
    assert 'from engine.delivery_freshness import evaluate_signal_age' in commands
    assert 'exceeds max 300s for crypto' not in commands


def test_rr_copy_labels_tp1_and_final_target() -> None:
    formatter = _source("signalrank_telegram/tier_signal_formatter.py")
    assert 'R/R: TP1 1:' in formatter


def test_admin_pulse_has_distributed_replica_lock() -> None:
    source = _source("engine/admin_pulse.py")
    assert 'ENGINE_PULSE_DISTRIBUTED_LOCK_ENABLED' in source
    assert 'client.set(key, token, nx=True, ex=ttl)' in source
    assert 'duplicate replica pulse skipped' in source



def test_provider_recovery_requires_stable_success_streak() -> None:
    source = _source("data/fetcher.py")
    assert 'PROVIDER_RECOVERY_REQUIRED_SUCCESSES' in source
    assert 'PROVIDER_RECOVERY_STABLE_SECONDS' in source
    assert '_PROVIDER_RECOVERY_SUCCESS_STREAK' in source
    assert '_PROVIDER_RECOVERY_FIRST_SUCCESS' in source
    assert 'stable_for >= _provider_recovery_stable_seconds()' in source


def test_v108_safe_defaults_are_declared() -> None:
    for rel in (
        ".env.example",
        "configs/env/railway-staging.env.example",
        "configs/env/railway-hobby-owner-beta.env.example",
    ):
        source = _source(rel)
        assert 'TELEGRAM_RICH_MESSAGES_CERTIFIED=0' in source, rel
        assert 'MONITOR_REFRESH_DB_TIMEOUT_SECONDS=2' in source, rel
        assert 'RESEND_JOB_TIMEOUT_SECONDS=90' in source, rel
        assert 'ENGINE_PULSE_DISTRIBUTED_LOCK_ENABLED=1' in source, rel
        assert 'PROVIDER_RECOVERY_REQUIRED_SUCCESSES=3' in source, rel
        assert 'PROVIDER_RECOVERY_STABLE_SECONDS=120' in source, rel
