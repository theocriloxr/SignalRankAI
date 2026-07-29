"""Runtime policy for Paystack test and guarded live-mode operations.

This module never contains credentials. It decides whether a checkout or
webhook mutation is permitted for the current environment, user, key mode and
amount. Production keeps its normal live-key behaviour. Railway staging may
use live keys only after two explicit acknowledgements and only for an
allowlisted test audience under a configured amount cap.
"""
from __future__ import annotations

import os
import hashlib
import hmac
from dataclasses import dataclass
from typing import Mapping, MutableMapping

_TRUTHY = {"1", "true", "yes", "on", "enabled"}
PAYSTACK_LIVE_STAGING_ACK_VALUE = "I_UNDERSTAND_PAYSTACK_LIVE_KEYS_MOVE_REAL_MONEY"


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in _TRUTHY


def _normalise_ack(value: object) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1].strip()
    return text


def _environment(env: Mapping[str, str]) -> str:
    return str(
        env.get("RAILWAY_ENVIRONMENT_NAME")
        or env.get("RAILWAY_ENVIRONMENT")
        or env.get("APP_ENV")
        or env.get("ENVIRONMENT")
        or "dev"
    ).strip().lower()


def _parse_ids(raw: object) -> set[int]:
    out: set[int] = set()
    for item in str(raw or "").replace(";", ",").split(","):
        token = item.strip()
        if not token:
            continue
        try:
            out.add(int(token))
        except (TypeError, ValueError):
            continue
    return out


def _allowed_ids(env: Mapping[str, str]) -> set[int]:
    raw = (
        env.get("PAYSTACK_LIVE_STAGING_ALLOWED_USER_IDS")
        or env.get("FULL_SYSTEM_TEST_USER_IDS")
        or env.get("DELIVERY_AUDIENCE_ALLOWLIST")
        or env.get("OWNER_TELEGRAM_ID")
        or env.get("TELEGRAM_OWNER_ID")
        or ""
    )
    return _parse_ids(raw)


def _max_amount(env: Mapping[str, str]) -> float:
    try:
        return max(1.0, float(env.get("PAYSTACK_LIVE_STAGING_MAX_AMOUNT_NGN") or 56000))
    except (TypeError, ValueError):
        return 56000.0


def is_paystack_live_staging_ack_valid(value: object) -> bool:
    return _normalise_ack(value) == PAYSTACK_LIVE_STAGING_ACK_VALUE


def live_staging_mode_valid(environ: Mapping[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    return bool(
        _environment(env) not in {"production", "prod"}
        and _truthy(env.get("FULL_SYSTEM_STAGING_TEST_ACTIVE"))
        and _truthy(env.get("PAYSTACK_LIVE_STAGING_ENABLED"))
        and is_paystack_live_staging_ack_valid(env.get("PAYSTACK_LIVE_STAGING_ACK"))
        and str(env.get("PAYSTACK_SECRET_KEY") or "").strip().startswith("sk_live_")
        and str(env.get("PAYSTACK_PUBLIC_KEY") or "").strip().startswith("pk_live_")
        and bool(_allowed_ids(env))
    )


@dataclass(frozen=True)
class PaystackOperationDecision:
    allowed: bool
    mode: str
    reason: str
    max_amount_ngn: float | None = None


def evaluate_paystack_operation(
    *,
    telegram_user_id: int | None = None,
    amount_ngn: float | int | None = None,
    environ: Mapping[str, str] | None = None,
) -> PaystackOperationDecision:
    """Return whether a checkout/webhook mutation is permitted.

    Test keys remain usable in non-production. Live keys in non-production
    require guarded live-staging mode, a matching user allowlist and an amount
    at or below the configured cap. Production is not rewritten by this policy.
    """
    env = environ if environ is not None else os.environ
    secret = str(env.get("PAYSTACK_SECRET_KEY") or "").strip()
    environment = _environment(env)
    if not secret:
        return PaystackOperationDecision(False, "missing", "paystack_secret_missing")

    if environment in {"production", "prod"}:
        mode = "live" if secret.startswith("sk_live_") else "test" if secret.startswith("sk_test_") else "unknown"
        return PaystackOperationDecision(True, mode, "production_policy")

    if secret.startswith("sk_test_"):
        return PaystackOperationDecision(True, "test", "test_key_allowed")

    if not secret.startswith("sk_live_"):
        return PaystackOperationDecision(False, "unknown", "unsupported_paystack_key_mode")

    if not live_staging_mode_valid(env):
        return PaystackOperationDecision(False, "live", "live_staging_ack_or_configuration_invalid", _max_amount(env))

    allowed = _allowed_ids(env)
    if telegram_user_id is None:
        return PaystackOperationDecision(False, "live", "telegram_user_id_required", _max_amount(env))
    try:
        user_id = int(telegram_user_id)
    except (TypeError, ValueError):
        return PaystackOperationDecision(False, "live", "telegram_user_id_invalid", _max_amount(env))
    if user_id not in allowed:
        return PaystackOperationDecision(False, "live", "telegram_user_not_allowlisted", _max_amount(env))

    limit = _max_amount(env)
    if amount_ngn is not None:
        try:
            amount = float(amount_ngn)
        except (TypeError, ValueError):
            return PaystackOperationDecision(False, "live", "amount_invalid", limit)
        if amount <= 0:
            return PaystackOperationDecision(False, "live", "amount_invalid", limit)
        if amount > limit:
            return PaystackOperationDecision(False, "live", f"amount_exceeds_live_staging_cap:{amount:.2f}>{limit:.2f}", limit)

    return PaystackOperationDecision(True, "live", "guarded_live_staging", limit)



def verify_paystack_event_signature(
    payload: bytes | str,
    signature: str | None,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Verify Paystack HMAC against the secret key and optional rotation key."""
    env = environ if environ is not None else os.environ
    if not signature:
        return False
    body = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
    candidates: list[str] = []
    for name in ("PAYSTACK_SECRET_KEY", "PAYSTACK_WEBHOOK_SECRET"):
        secret = str(env.get(name) or "").strip()
        if secret and secret not in candidates:
            candidates.append(secret)
    for secret in candidates:
        computed = hmac.new(secret.encode("utf-8"), body, hashlib.sha512).hexdigest()
        if hmac.compare_digest(computed, str(signature).strip()):
            return True
    return False


def apply_live_staging_runtime_markers(environ: MutableMapping[str, str] | None = None) -> None:
    env = environ if environ is not None else os.environ
    active = live_staging_mode_valid(env)
    env["PAYSTACK_LIVE_STAGING_ACTIVE"] = "1" if active else "0"
    if active:
        env["PAYMENTS_PUBLIC_TEST_MODE"] = "0"


__all__ = [
    "PAYSTACK_LIVE_STAGING_ACK_VALUE",
    "PaystackOperationDecision",
    "apply_live_staging_runtime_markers",
    "evaluate_paystack_operation",
    "is_paystack_live_staging_ack_valid",
    "live_staging_mode_valid",
    "verify_paystack_event_signature",
]
