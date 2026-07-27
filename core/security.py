"""Security primitives shared by web, token, payment, and broker boundaries."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from typing import Any

from core.env import Environment, environment


_SECRET_FIELDS = re.compile(
    r"(authorization|api[_-]?key|api[_-]?secret|password|secret|token|credential|signature)",
    re.IGNORECASE,
)


def constant_time_equal(left: str | bytes, right: str | bytes) -> bool:
    left_bytes = left if isinstance(left, bytes) else str(left or "").encode("utf-8")
    right_bytes = right if isinstance(right, bytes) else str(right or "").encode("utf-8")
    return hmac.compare_digest(left_bytes, right_bytes)


def fingerprint(value: str, *, purpose: str = "generic") -> str:
    payload = f"{purpose}:{str(value or '')}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


def api_token_pepper() -> str:
    pepper = str(os.getenv("API_TOKEN_PEPPER") or "").strip()
    if pepper:
        return pepper
    if environment() in {Environment.STAGING, Environment.PRODUCTION}:
        raise RuntimeError("API_TOKEN_PEPPER is required outside dev/test")
    return "signalrankai-dev-only-token-pepper"


def redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "<redacted>" if _SECRET_FIELDS.search(str(key)) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    return value


__all__ = [
    "api_token_pepper",
    "constant_time_equal",
    "fingerprint",
    "redact_secrets",
]
