from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from pathlib import Path


def _live_staging_env() -> dict[str, str]:
    return {
        "APP_ENV": "staging",
        "FULL_SYSTEM_STAGING_TEST_MODE": "1",
        "FULL_SYSTEM_STAGING_TEST_ACK": "I_UNDERSTAND_STAGING_TESTS_CAN_TRIGGER_EXTERNAL_ACTIONS",
        "FULL_SYSTEM_TEST_USER_IDS": "1409578077",
        "PAYSTACK_LIVE_STAGING_ENABLED": "1",
        "PAYSTACK_LIVE_STAGING_ACK": "I_UNDERSTAND_PAYSTACK_LIVE_KEYS_MOVE_REAL_MONEY",
        "PAYSTACK_LIVE_STAGING_ALLOWED_USER_IDS": "1409578077",
        "PAYSTACK_LIVE_STAGING_MAX_AMOUNT_NGN": "56000",
        "PAYSTACK_SECRET_KEY": "sk_live_forbidden_example",
        "PAYSTACK_PUBLIC_KEY": "pk_live_forbidden_example",
    }


def test_production_live_paystack_semantics_remain_enabled():
    from payments.paystack_policy import evaluate_paystack_operation

    decision = evaluate_paystack_operation(
        telegram_user_id=1409578077,
        amount_ngn=1000,
        environ={"APP_ENV": "production", "PAYSTACK_SECRET_KEY": "sk_live_production_example"},
    )
    assert decision.allowed
    assert decision.mode == "live"
    assert decision.reason == "production_policy"

def test_live_paystack_staging_is_retired_and_fails_closed():
    from runtime_safety import apply_runtime_safety_environment

    env = _live_staging_env()
    result = apply_runtime_safety_environment(env)
    assert result.full_system_test_enabled is True
    assert env["PAYSTACK_LIVE_STAGING_ACTIVE"] == "0"
    assert env["PAYMENTS_PUBLIC_TEST_MODE"] == "1"
    assert env["PAYMENTS_ENABLED"] == "0"
    assert env["PAYMENTS_PUBLIC_ENABLED"] == "0"
    assert env["REAL_PAYOUTS_ENABLED"] == "0"
    assert "PAYSTACK_LIVE_KEY_REJECTED" in result.hard_boundaries


def test_live_paystack_staging_invalid_second_ack_fails_money_paths_closed():
    from runtime_safety import apply_runtime_safety_environment

    env = _live_staging_env()
    env["PAYSTACK_LIVE_STAGING_ACK"] = "wrong"
    result = apply_runtime_safety_environment(env)
    assert result.full_system_test_enabled is True
    assert env["PAYSTACK_LIVE_STAGING_ACTIVE"] == "0"
    assert env["PAYMENTS_ENABLED"] == "0"
    assert env["PAYMENTS_PUBLIC_ENABLED"] == "0"
    assert env["REAL_PAYOUTS_ENABLED"] == "0"
    assert "PAYSTACK_LIVE_STAGING_NOT_ENABLED" in result.hard_boundaries


def test_live_paystack_policy_rejects_every_staging_user_and_amount():
    from payments.paystack_policy import evaluate_paystack_operation
    from runtime_safety import apply_runtime_safety_environment

    env = _live_staging_env()
    apply_runtime_safety_environment(env)
    for user_id, amount in ((1409578077, 56000), (999, 1000), (1409578077, 56001)):
        decision = evaluate_paystack_operation(telegram_user_id=user_id, amount_ngn=amount, environ=env)
        assert not decision.allowed
        assert decision.reason == "live_staging_ack_or_configuration_invalid"


def test_paystack_signature_accepts_secret_key_even_when_rotation_value_differs():
    from payments.paystack_policy import verify_paystack_event_signature

    payload = b'{"event":"charge.success"}'
    env = {
        "PAYSTACK_SECRET_KEY": "sk_live_forbidden_example",
        "PAYSTACK_WEBHOOK_SECRET": "different_rotation_value",
    }
    signature = hmac.new(env["PAYSTACK_SECRET_KEY"].encode(), payload, hashlib.sha512).hexdigest()
    assert verify_paystack_event_signature(payload, signature, env)


def test_adaptive_helpers_root_compatibility_imports():
    from engine.adaptive.helpers import atr, confirmed_pivots, fingerprint, ohlcv, targets

    for value in (atr, confirmed_pivots, fingerprint, ohlcv, targets):
        assert callable(value)


def test_rejection_features_are_recursively_json_safe():
    from engine.signal_deduplicator import _json_safe, get_ml_rejection_tracker

    stamp = datetime(2026, 7, 29, 22, 26, tzinfo=timezone.utc)
    payload = _json_safe({"nested": {"created_at": stamp}, "items": [stamp]})
    assert payload["nested"]["created_at"] == stamp.isoformat()
    assert payload["items"][0] == stamp.isoformat()
    assert get_ml_rejection_tracker() is get_ml_rejection_tracker()


def test_rejection_learning_uses_ml_tracker_not_signal_deduplicator():
    root = Path(__file__).resolve().parents[1]
    source = (root / "engine" / "rejection_learning.py").read_text(encoding="utf-8")
    assert "get_ml_rejection_tracker" in source
    assert "get_deduplicator().persist_rejection" not in source


def test_commodity_ghost_price_bounds_reject_wrong_wti_instrument():
    from data.fetcher import validate_price_sanity

    assert validate_price_sanity("WTI", 84.30)
    assert not validate_price_sanity("WTI", 3.535)
    assert validate_price_sanity("XAUUSD", 4133.10)
    assert not validate_price_sanity("XAUUSD", 84.30)


def test_staging_freshness_advisory_is_visible_and_live_execution_blocked():
    root = Path(__file__).resolve().parents[1]
    source = (root / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    assert "TEST ONLY — NOT EXECUTION ELIGIBLE" in source
    assert "STAGING_DELIVERY_FRESHNESS_ADVISORY" in source
    assert 'signal["live_execution_blocked"] = True' in source
    assert "[autoexec] blocked staging/test-only signal" in source


def test_v125_profile_contains_guarded_live_paystack_settings():
    root = Path(__file__).resolve().parents[1]
    profile = (root / "SignalRankAI_v1.3.2_Railway_Full_System_Live_Paystack_Staging.env.example").read_text(encoding="utf-8")
    for line in (
        "APP_VERSION=1.3.2",
        "PAYMENTS_PUBLIC_TEST_MODE=0",
        "PAYSTACK_LIVE_STAGING_ENABLED=1",
        "PAYSTACK_LIVE_STAGING_ACK=I_UNDERSTAND_PAYSTACK_LIVE_KEYS_MOVE_REAL_MONEY",
        "PAYSTACK_LIVE_STAGING_ALLOWED_USER_IDS=1409578077",
        "PAYSTACK_LIVE_STAGING_MAX_AMOUNT_NGN=56000",
        "STAGING_DELIVERY_FRESHNESS_ADVISORY=1",
    ):
        assert line in profile


def test_version_fingerprint_is_v125():
    from core.version import APP_VERSION, RELEASE_FINGERPRINT

    assert APP_VERSION == "1.3.6.5"
    assert RELEASE_FINGERPRINT == "v1.3.6.5-production-integrity-hardening-20260802"
