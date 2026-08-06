from __future__ import annotations

import base64
import os
import time
from pathlib import Path

import pytest

from services.platform.email_delivery import render_account_email
from services.platform.identity import AuthenticationError, _totp_code, verify_totp

ROOT = Path(__file__).resolve().parents[1]


def test_0038_is_the_single_successor_of_0037() -> None:
    text = (ROOT / "db/migrations/versions/0038_account_security_product_completion.py").read_text()
    assert 'down_revision = "0037_unified_product_workspaces"' in text
    for table in (
        "email_outbox",
        "user_mfa_totp",
        "account_recovery_codes",
        "notification_events",
        "organization_audit_events",
        "user_alerts",
        "app_feature_flags",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in text


def test_account_email_templates_never_include_secret_fields() -> None:
    subject, plain, html = render_account_email(
        "password_reset",
        {"link": "https://app.example/reset?token=one-time", "expires_minutes": 20},
    )
    assert "Reset" in subject
    assert "one-time" in plain
    assert "password hash" not in plain.lower()
    assert "private key" not in html.lower()


def test_totp_verification_and_replay_guard() -> None:
    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    code, step = _totp_code(secret, at_time=int(time.time()))
    matched = verify_totp(secret, code, window=1)
    assert abs(matched - step) <= 1
    with pytest.raises(AuthenticationError, match="reused"):
        verify_totp(secret, code, window=1, last_used_step=matched)


def test_platform_routes_include_recovery_mfa_and_product_completion() -> None:
    from web.platform_api import router

    routes = {route.path for route in router.routes}
    expected = {
        "/platform/auth/magic-link/request",
        "/platform/auth/magic-link/complete",
        "/platform/auth/password-reset/request",
        "/platform/auth/password-reset/complete",
        "/platform/auth/email-verification/request",
        "/platform/auth/email-verification/complete",
        "/platform/auth/mfa/complete",
        "/platform/security/mfa/setup",
        "/platform/security/mfa/enable",
        "/platform/security/mfa/disable",
        "/platform/profile",
        "/platform/portfolio",
        "/platform/performance",
        "/platform/billing",
        "/platform/notifications",
        "/platform/alerts",
    }
    assert expected <= routes


def test_worker_owns_transactional_email_outbox() -> None:
    text = (ROOT / "worker/worker.py").read_text()
    assert "EMAIL_DELIVERY_ENABLED" in text
    assert "deliver_email_outbox_batch" in text


def test_web_client_escapes_server_data_and_supports_new_views() -> None:
    js = (ROOT / "web/platform_app/app.js").read_text()
    html = (ROOT / "web/platform_app/index.html").read_text()
    assert "const esc=" in js
    for view in ("portfolioView", "performanceView", "supportView"):
        assert view in html
    assert "/auth/mfa/complete" in js
    assert "/auth/password-reset/request" in js


def test_mobile_client_supports_mfa_recovery_and_full_product_views() -> None:
    app = (ROOT / "mobile/App.tsx").read_text()
    api = (ROOT / "mobile/src/api.ts").read_text()
    for screen in ("portfolio", "performance", "support"):
        assert f"'{screen}'" in app
    assert "completeMfa" in api
    assert "requestMagicLink" in api
    assert "completePasswordReset" in api


def test_new_runtime_secrets_remain_unset_in_example() -> None:
    env = (ROOT / ".env.example").read_text()
    assert "SMTP_PASSWORD=\n" in env
    assert "APP_AUTH_SECRET=\n" in env
    assert "REAL_EXECUTION_ENABLED=0" in env
    assert "PAYSTACK_TRANSFERS_ENABLED=0" in env


def test_code_version_advanced_to_150() -> None:
    text = (ROOT / "core/version.py").read_text()
    assert 'CODE_VERSION = "1.5.0"' in text
    assert "unified-ecosystem-completion" in text
