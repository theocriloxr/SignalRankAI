"""Environment-parity regression tests (Phases 3-6, 22).

Covers the canonical capability resolver, staging/production payment and
telegram modes, trading/payout safety modes, and the parity health report.
"""

from __future__ import annotations

import os

import pytest


def _env(**overrides: str) -> dict[str, str]:
    base = {
        "RAILWAY_ENVIRONMENT_NAME": "staging",
        "PAYMENTS_ENABLED": "1",
        "PAYMENTS_PUBLIC_ENABLED": "0",
        "PAYMENTS_PUBLIC_TEST_MODE": "1",
        "PAYSTACK_WEBHOOK_RECOVERY_ENABLED": "1",
        "PAYSTACK_SECRET_KEY": "sk_test_example",
        "PAYSTACK_PUBLIC_KEY": "pk_test_example",
        "PAYSTACK_WEBHOOK_SECRET": "sk_test_example",
        "STAGING_TELEGRAM_BOT_TOKEN": "123:staging-token",
        "REAL_EXECUTION_ENABLED": "0",
        "REAL_PAYOUTS_ENABLED": "0",
        "PAPER_TRADING_ENABLED": "1",
    }
    base.update(overrides)
    return base


def test_staging_resolves_test_payments_and_staging_bot() -> None:
    from core.capability_resolver import resolve_capabilities

    report = resolve_capabilities(_env())
    assert report.environment == "staging"
    assert report.payments_mode == "test"
    assert report.payments_enabled is True
    assert report.payments_public_enabled is False
    assert report.paystack_recovery_enabled is True
    assert report.telegram_mode == "staging_bot"
    assert report.trading_mode == "paper"
    assert report.payout_mode == "disabled"


def test_production_with_live_keys_resolves_live_mode() -> None:
    from core.capability_resolver import resolve_capabilities

    report = resolve_capabilities(
        _env(
            RAILWAY_ENVIRONMENT_NAME="production",
            PAYMENTS_PUBLIC_ENABLED="1",
            PAYMENTS_PUBLIC_TEST_MODE="0",
            PAYSTACK_SECRET_KEY="sk_live_example",
            PAYSTACK_PUBLIC_KEY="pk_live_example",
            PAYSTACK_WEBHOOK_SECRET="sk_live_example",
            STAGING_TELEGRAM_BOT_TOKEN="",
            TELEGRAM_BOT_TOKEN="123:prod-token",
        )
    )
    assert report.environment == "production"
    assert report.payments_mode == "live"
    assert report.payments_public_enabled is True
    assert report.telegram_mode == "production_bot"


def test_mixed_key_modes_are_rejected_as_mismatch() -> None:
    from core.capability_resolver import resolve_capabilities

    report = resolve_capabilities(
        _env(
            PAYSTACK_SECRET_KEY="sk_test_example",
            PAYSTACK_PUBLIC_KEY="pk_live_example",
        )
    )
    assert report.payments_mode == "mismatch"
    assert "paystack_key_mode_mismatch" in report.safe_reasons


def test_staging_never_uses_production_bot_token() -> None:
    from core.capability_resolver import telegram_mode

    assert telegram_mode(_env(STAGING_TELEGRAM_BOT_TOKEN="staging-only")) == "staging_bot"
    # Even if the production token is set, staging stays on the staging bot.
    assert (
        telegram_mode(
            _env(
                STAGING_TELEGRAM_BOT_TOKEN="123:staging",
                TELEGRAM_BOT_TOKEN="123:production",
            )
        )
        == "staging_bot"
    )


def test_staging_without_staging_token_fails_closed() -> None:
    from core.capability_resolver import telegram_mode

    # Staging with only the shared production token must NOT attach it.
    assert telegram_mode(_env(STAGING_TELEGRAM_BOT_TOKEN="", TELEGRAM_BOT_TOKEN="123:prod")) == "misconfigured"
    assert telegram_mode(_env(STAGING_TELEGRAM_BOT_TOKEN="")) == "no_token"


def test_production_with_staging_token_is_misconfigured() -> None:
    from core.capability_resolver import telegram_mode

    assert (
        telegram_mode(
            _env(
                RAILWAY_ENVIRONMENT_NAME="production",
                TELEGRAM_BOT_TOKEN="",
                STAGING_TELEGRAM_BOT_TOKEN="123:staging",
            )
        )
        == "misconfigured"
    )


def test_trading_mode_guards_live_activation() -> None:
    from core.capability_resolver import trading_mode

    assert trading_mode(environ=_env()) == "paper"
    assert (
        trading_mode(environ=_env(REAL_EXECUTION_ENABLED="1"))
        in {"live_guarded", "live_disabled"}
    )


def test_payout_mode_requires_explicit_enable() -> None:
    from core.capability_resolver import payout_mode

    assert payout_mode(environ=_env()) == "disabled"
    assert payout_mode(environ=_env(REAL_PAYOUTS_ENABLED="1")) in {
        "sandbox",
        "live_guarded",
    }


def test_service_role_resolution() -> None:
    from core.capability_resolver import service_role

    assert service_role({"RUN_MODE": "worker"}) == "worker"
    assert service_role({"SERVICE_ROLE": "front-door"}) == "frontdoor"
    assert service_role({"RUN_MODE": "migration"}) == "migration"
    assert service_role({}) == "all"


def test_migration_single_expected_head() -> None:
    from core.capability_resolver import migration_revisions

    expected, current = migration_revisions()
    assert expected == "0034_production_integrity"
    assert current is None  # DB not required for the resolver


def test_parity_report_exposes_no_secrets() -> None:
    from core.capability_resolver import resolve_capabilities

    report = resolve_capabilities(_env())
    payload = report.as_dict()
    text = str(payload)
    assert "sk_test_example" not in text
    assert "pk_test_example" not in text
    assert "staging-token" not in text
    assert "PAYSTACK_SECRET_KEY" not in text


def test_staging_profile_has_paystack_recovery_enabled() -> None:
    from pathlib import Path

    profile = Path("configs/env/railway-staging.env.example").read_text(encoding="utf-8")
    assert "PAYSTACK_WEBHOOK_RECOVERY_ENABLED=1" in profile
    assert "PAYMENTS_ENABLED=1" in profile
    assert "PAYMENTS_PUBLIC_TEST_MODE=1" in profile
    assert "PAYSTACK_SECRET_KEY=sk_test_" in profile
    assert "STAGING_TELEGRAM_BOT_TOKEN=" in profile


def test_production_profile_has_live_contract() -> None:
    from pathlib import Path

    profile = Path("configs/env/production.env.example").read_text(encoding="utf-8")
    assert "PAYSTACK_SECRET_KEY=sk_live_" in profile
    assert "PAYMENTS_PUBLIC_TEST_MODE=0" in profile
    assert "PAYSTACK_WEBHOOK_RECOVERY_ENABLED=1" in profile
    assert "RAILWAY_ENVIRONMENT_NAME=production" in profile


def test_parity_health_script_runs() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "scripts/verify_environment_parity.py", "--json"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"environment"' in result.stdout
