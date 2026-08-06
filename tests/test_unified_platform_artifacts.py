from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_unified_identity_migration_follows_ecosystem_head() -> None:
    text = (ROOT / "db/migrations/versions/0036_unified_platform_identity.py").read_text()
    assert 'down_revision = "0035_staging_certification_ecosystem"' in text
    for table in (
        "auth_identities",
        "password_credentials",
        "user_sessions",
        "login_challenges",
        "account_link_requests",
        "account_merge_records",
        "push_devices",
        "organizations",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in text


def test_legacy_numeric_user_login_is_removed() -> None:
    text = (ROOT / "web/userdash/app.py").read_text().lower()
    assert "user_id.isdigit" not in text
    assert "redirect" in text
    assert '"/app"' in text or "'/app'" in text


def test_pwa_does_not_cache_private_api() -> None:
    text = (ROOT / "web/platform_app/service-worker.js").read_text()
    assert "/api/" in text
    assert "cache" in text.lower()


def test_mobile_uses_current_expo_and_secure_store() -> None:
    package = json.loads((ROOT / "mobile/package.json").read_text())
    assert package["dependencies"]["expo"].startswith("~57")
    assert "expo-secure-store" in package["dependencies"]
    assert "expo-notifications" in package["dependencies"]
    assert "expo-router" not in package["dependencies"]
    api = (ROOT / "mobile/src/api.ts").read_text()
    assert "SecureStore" in api
    assert "createTelegramLink" in api


def test_dynamic_universe_has_no_driver_specific_array_cast() -> None:
    text = (ROOT / "data/database_universe.py").read_text()
    assert "database" in text.lower()
    assert "ANY(CAST" not in text
    assert "provider_instruments" in text


def test_push_tokens_are_application_encrypted() -> None:
    text = (ROOT / "web/platform_api.py").read_text()
    assert "encrypt_secret(payload.push_token)" in text
    assert 'detail="Push registration requires ENCRYPTION_KEY"' in text
    assert '"token": payload.push_token' not in text


def test_bidirectional_telegram_linking_exists() -> None:
    identity = (ROOT / "services/platform/identity.py").read_text()
    api = (ROOT / "web/platform_api.py").read_text()
    commands = (ROOT / "signalrank_telegram/commands.py").read_text()
    assert "create_telegram_link_request" in identity
    assert "complete_telegram_link_request" in identity
    assert '/account/telegram-link' in api
    assert "async def link_command" in commands
    assert "pending_review" in identity


def test_execution_and_payout_kill_switch_defaults_remain_off() -> None:
    env = (ROOT / ".env.example").read_text()
    for name in (
        "REAL_EXECUTION_ENABLED=0",
        "AUTO_EXECUTION_ENABLED=0",
        "COPY_TRADE_ENABLED=0",
        "REAL_PAYOUTS_ENABLED=0",
        "PAYSTACK_TRANSFERS_ENABLED=0",
    ):
        assert name in env


def test_product_workspace_migration_is_head_successor() -> None:
    text = (ROOT / "db/migrations/versions/0037_unified_product_workspaces.py").read_text()
    assert 'down_revision = "0036_unified_platform_identity"' in text
    for table in ("journal_entries", "api_keys", "webhook_deliveries", "support_tickets", "analytics_events"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in text


def test_professional_api_and_webhook_worker_are_wired() -> None:
    api = (ROOT / "web/platform_api.py").read_text()
    worker = (ROOT / "worker/worker.py").read_text()
    delivery = (ROOT / "db/pg_features.py").read_text()
    assert '/professional/signals' in api
    assert '/api-keys' in api
    assert '/webhooks' in api
    assert 'WEBHOOK_DELIVERY_ENABLED' in worker
    assert 'queue_user_webhook_event' in delivery
