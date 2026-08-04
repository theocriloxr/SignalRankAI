"""Regression tests for the canonical Paystack configuration resolver."""
from __future__ import annotations

import pytest

from payments.payment_config import resolve_paystack_configuration


def _env(**overrides: str) -> dict[str, str]:
    base = {
        "PAYMENTS_ENABLED": "1",
        "PAYMENTS_PUBLIC_ENABLED": "1",
        "PAYMENTS_PUBLIC_TEST_MODE": "0",
        "PAYSTACK_WEBHOOK_RECOVERY_ENABLED": "1",
        "APP_ENV": "production",
        "PAYSTACK_SECRET_KEY": "sk_live_example",
        "PAYSTACK_PUBLIC_KEY": "pk_live_example",
        "PAYSTACK_WEBHOOK_SECRET": "whsec_example",
    }
    base.update(overrides)
    return base


def test_test_key_staging_checkout_is_allowed() -> None:
    cfg = resolve_paystack_configuration(_env(
        APP_ENV="staging",
        PAYSTACK_SECRET_KEY="sk_test_example",
        PAYSTACK_PUBLIC_KEY="pk_test_example",
    ))
    assert cfg.key_mode == "test"
    assert cfg.checkout_policy_allowed is True
    assert cfg.checkout_policy_reason == "test_key_allowed"


def test_live_public_staging_checkout_is_blocked() -> None:
    cfg = resolve_paystack_configuration(_env(
        APP_ENV="staging",
        PAYSTACK_SECRET_KEY="sk_live_example",
        PAYSTACK_PUBLIC_KEY="pk_live_example",
    ))
    assert cfg.key_mode == "live"
    assert cfg.checkout_policy_allowed is False
    assert cfg.checkout_policy_reason == "live_staging_ack_or_configuration_invalid"


def test_live_production_checkout_is_allowed_with_valid_config() -> None:
    cfg = resolve_paystack_configuration(_env())
    assert cfg.key_mode == "live"
    assert cfg.checkout_policy_allowed is True
    assert cfg.checkout_policy_reason == "production_policy"


def test_mixed_key_modes_are_rejected() -> None:
    cfg = resolve_paystack_configuration(_env(
        PAYSTACK_SECRET_KEY="sk_live_example",
        PAYSTACK_PUBLIC_KEY="pk_test_example",
    ))
    assert cfg.key_mode == "mismatch"
    assert cfg.checkout_policy_allowed is False
    assert cfg.checkout_policy_reason == "paystack_key_mode_mismatch"


def test_missing_secret_is_unavailable() -> None:
    cfg = resolve_paystack_configuration(_env(PAYSTACK_SECRET_KEY=""))
    assert cfg.key_mode == "missing"
    assert cfg.secret_key_present is False
    assert cfg.checkout_policy_allowed is False
    assert cfg.checkout_policy_reason == "paystack_secret_missing"


def test_invalid_secret_prefix_is_rejected() -> None:
    cfg = resolve_paystack_configuration(_env(PAYSTACK_SECRET_KEY="not-a-paystack-key"))
    assert cfg.key_mode == "invalid"
    assert cfg.checkout_policy_allowed is False
    assert cfg.checkout_policy_reason == "unsupported_paystack_key_mode"


def test_payments_disabled_blocks_checkout() -> None:
    cfg = resolve_paystack_configuration(_env(PAYMENTS_ENABLED="0"))
    assert cfg.checkout_policy_allowed is False
    assert cfg.checkout_policy_reason == "payments_disabled"


def test_test_key_in_production_is_blocked() -> None:
    cfg = resolve_paystack_configuration(_env(
        APP_ENV="production",
        PAYSTACK_SECRET_KEY="sk_test_example",
        PAYSTACK_PUBLIC_KEY="pk_test_example",
    ))
    assert cfg.key_mode == "test"
    assert cfg.checkout_policy_allowed is False
    assert cfg.checkout_policy_reason == "test_key_in_production"


def test_worker_recovery_uses_secret_only_configuration() -> None:
    # The worker recovery path only needs the secret; a missing public key must
    # not flip key mode to mismatch (public absent is allowed).
    cfg = resolve_paystack_configuration(_env(
        APP_ENV="staging",
        PAYSTACK_SECRET_KEY="sk_test_example",
        PAYSTACK_PUBLIC_KEY="",
    ))
    assert cfg.key_mode == "test"
    assert cfg.public_key_present is False
    assert cfg.checkout_policy_allowed is True


def test_diagnostics_never_include_secret_values() -> None:
    cfg = resolve_paystack_configuration(_env(PAYSTACK_SECRET_KEY="sk_live_topsecret123"))
    diag = cfg.as_diagnostics()
    serialized = str(diag)
    assert "topsecret" not in serialized
    assert "sk_live_topsecret123" not in serialized
    assert diag["secret_key_present"] is True
