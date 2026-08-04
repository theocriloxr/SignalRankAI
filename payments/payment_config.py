"""Canonical Paystack configuration resolver.

Single source of truth for Paystack/payment runtime decisions shared by the
Telegram front door, checkout initialization, the FastAPI webhook route,
payment verification, and the worker recovery loop.

This module never exposes secret values. It reports presence/mode booleans and
safe machine-readable reasons only.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

_TRUTHY = {"1", "true", "yes", "y", "on", "enabled"}


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in _TRUTHY


def _clean_key(value: object) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1].strip()
    return text


def _environment(env: Mapping[str, str]) -> str:
    raw = str(
        env.get("RAILWAY_ENVIRONMENT_NAME")
        or env.get("RAILWAY_ENVIRONMENT")
        or env.get("APP_ENV")
        or env.get("ENVIRONMENT")
        or "dev"
    ).strip().lower()
    aliases = {"prod": "production", "development": "dev", "preview": "staging"}
    return aliases.get(raw, raw or "dev")


def _key_prefix(value: object) -> str | None:
    cleaned = _clean_key(value)
    if not cleaned:
        return None
    if cleaned.startswith("sk_test_") or cleaned.startswith("pk_test_"):
        return "test"
    if cleaned.startswith("sk_live_") or cleaned.startswith("pk_live_"):
        return "live"
    return "invalid"


@dataclass(frozen=True, slots=True)
class PaystackConfiguration:
    environment: str
    payments_enabled: bool
    payments_public_enabled: bool
    payments_public_test_mode: bool
    webhook_recovery_enabled: bool
    secret_key_present: bool
    public_key_present: bool
    webhook_signature_key_present: bool
    secret_prefix: str | None
    public_prefix: str | None
    key_mode: str  # test | live | missing | mismatch | invalid
    checkout_policy_allowed: bool
    checkout_policy_reason: str | None

    def as_diagnostics(self) -> dict[str, object]:
        """Redacted startup diagnostics — never includes key material."""
        return {
            "environment": self.environment,
            "payments_enabled": self.payments_enabled,
            "payments_public_enabled": self.payments_public_enabled,
            "payments_public_test_mode": self.payments_public_test_mode,
            "webhook_recovery_enabled": self.webhook_recovery_enabled,
            "secret_key_present": self.secret_key_present,
            "public_key_present": self.public_key_present,
            "webhook_signature_key_present": self.webhook_signature_key_present,
            "key_mode": self.key_mode,
            "checkout_policy_allowed": self.checkout_policy_allowed,
            "checkout_policy_reason": self.checkout_policy_reason,
        }


def resolve_paystack_configuration(
    environ: Mapping[str, str] | None = None,
) -> PaystackConfiguration:
    """Resolve the full Paystack runtime configuration without secrets.

    Key mode rules:
      - sk_test_ + pk_test_             -> test
      - sk_live_ + pk_live_             -> live
      - mixed prefixes                  -> mismatch
      - missing secret                  -> missing
      - any invalid prefix              -> invalid
    """
    env = environ if environ is not None else os.environ
    environment = _environment(env)
    secret = _clean_key(env.get("PAYSTACK_SECRET_KEY"))
    public = _clean_key(env.get("PAYSTACK_PUBLIC_KEY"))
    webhook_secret = _clean_key(env.get("PAYSTACK_WEBHOOK_SECRET"))

    secret_prefix = _key_prefix(secret)
    public_prefix = _key_prefix(public) if public else None

    payments_enabled = _truthy(env.get("PAYMENTS_ENABLED"))
    public_enabled = _truthy(env.get("PAYMENTS_PUBLIC_ENABLED"))
    public_test_mode = _truthy(env.get("PAYMENTS_PUBLIC_TEST_MODE"))
    recovery_enabled = _truthy(env.get("PAYSTACK_WEBHOOK_RECOVERY_ENABLED"))

    if secret_prefix is None:
        key_mode = "missing"
    elif secret_prefix == "invalid":
        key_mode = "invalid"
    elif public and public_prefix != secret_prefix:
        key_mode = "mismatch"
    else:
        key_mode = secret_prefix  # test | live

    allowed, reason = _checkout_policy(
        env=env,
        environment=environment,
        payments_enabled=payments_enabled,
        public_enabled=public_enabled,
        public_test_mode=public_test_mode,
        key_mode=key_mode,
        secret_prefix=secret_prefix,
    )

    return PaystackConfiguration(
        environment=environment,
        payments_enabled=payments_enabled,
        payments_public_enabled=public_enabled,
        payments_public_test_mode=public_test_mode,
        webhook_recovery_enabled=recovery_enabled,
        secret_key_present=bool(secret),
        public_key_present=bool(public),
        webhook_signature_key_present=bool(webhook_secret),
        secret_prefix=secret_prefix,
        public_prefix=public_prefix,
        key_mode=key_mode,
        checkout_policy_allowed=allowed,
        checkout_policy_reason=reason,
    )


def _checkout_policy(
    *,
    env: Mapping[str, str],
    environment: str,
    payments_enabled: bool,
    public_enabled: bool,
    public_test_mode: bool,
    key_mode: str,
    secret_prefix: str | None,
) -> tuple[bool, str | None]:
    """Decide whether a public checkout may be initialized in this runtime."""
    if not payments_enabled:
        return False, "payments_disabled"
    if key_mode == "missing":
        return False, "paystack_secret_missing"
    if key_mode == "invalid":
        return False, "unsupported_paystack_key_mode"
    if key_mode == "mismatch":
        return False, "paystack_key_mode_mismatch"
    if secret_prefix is None:
        return False, "paystack_secret_missing"

    if key_mode == "test":
        # Test checkout works in any non-production environment. It is never
        # interpreted as a public live payment.
        if environment in {"production", "prod"}:
            return False, "test_key_in_production"
        return True, "test_key_allowed"

    # key_mode == "live"
    if environment in {"production", "prod"}:
        if not public_enabled:
            return False, "payments_public_disabled"
        if public_test_mode:
            return False, "live_public_checkout_in_test_mode"
        return True, "production_policy"

    # Live keys outside production require guarded live staging: explicit enable
    # flag, exact acknowledgement, owner allowlist, and amount cap. Those are
    # enforced per-operation by payments.paystack_policy; here we only verify the
    # environment contract is even configured.
    from payments.paystack_policy import live_staging_mode_valid

    if not live_staging_mode_valid(env):
        return False, "live_staging_ack_or_configuration_invalid"
    if public_test_mode:
        return False, "live_public_checkout_in_test_mode"
    return True, "guarded_live_staging"


__all__ = [
    "PaystackConfiguration",
    "resolve_paystack_configuration",
]
