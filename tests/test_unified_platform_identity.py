from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from core.tier_policy import evaluate_feature_access, get_entitlements, tier_rank
from ml.schema_version import CRITICAL_FEATURES_V3, FEATURE_COLUMNS_V3, FEATURE_SCHEMA_VERSION, migrate_feature_payload
from services.platform.identity import (
    AuthenticationError,
    decode_access_token,
    encode_access_token,
    hash_password,
    validate_password,
    validate_telegram_login_payload,
    validate_telegram_mini_app_init_data,
    verify_password,
)


def test_password_hash_is_salted_and_verifiable() -> None:
    password = "StrongPass!2040"
    first = hash_password(password)
    second = hash_password(password)
    assert first != second
    assert verify_password(password, first)
    assert not verify_password("wrong", first)
    assert "StrongPass" not in first


@pytest.mark.parametrize("password", ["short", "alllowercaseonly", "123456789012345", "NOLOWERCASE123"])
def test_password_policy_rejects_weak_values(password: str) -> None:
    with pytest.raises(ValueError):
        validate_password(password)


def test_access_token_tampering_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_AUTH_SECRET", "x" * 64)
    token = encode_access_token(42, session_id="session-1")
    claims = decode_access_token(token)
    assert claims["user_id"] == 42
    assert claims["sid"] == "session-1"
    head, body, signature = token.split(".")
    tampered = f"{head}.{body}.{signature[:-1]}A"
    with pytest.raises(AuthenticationError):
        decode_access_token(tampered)


def test_telegram_login_widget_hmac_validation() -> None:
    bot_token = "123456:TEST_BOT_TOKEN"
    payload = {"id": "99", "first_name": "Emmanuel", "auth_date": str(int(time.time()))}
    check = "\n".join(f"{key}={payload[key]}" for key in sorted(payload))
    secret = hashlib.sha256(bot_token.encode()).digest()
    payload["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    result = validate_telegram_login_payload(payload, bot_token)
    assert result["id"] == "99"
    payload["hash"] = "0" * 64
    with pytest.raises(AuthenticationError):
        validate_telegram_login_payload(payload, bot_token)


def test_telegram_mini_app_hmac_validation() -> None:
    bot_token = "123456:TEST_BOT_TOKEN"
    values = {
        "auth_date": str(int(time.time())),
        "query_id": "AAE",
        "user": json.dumps({"id": 99, "first_name": "Emmanuel"}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    result = validate_telegram_mini_app_init_data(urlencode(values), bot_token)
    assert result["user"]["id"] == 99


def test_tier_expansion_and_entitlements() -> None:
    assert tier_rank("professional") > tier_rank("vip")
    assert tier_rank("institutional") > tier_rank("professional")
    assert get_entitlements("professional").has("rest_api")
    assert get_entitlements("institutional").has("organization_tenancy")
    assert not evaluate_feature_access("free", "rest_api").allowed


def test_feature_schema_is_versioned_and_strict_when_requested() -> None:
    assert FEATURE_SCHEMA_VERSION.startswith("feature-schema-v")
    migrated = migrate_feature_payload({"score_normalized": 0.8}, ["score_normalized"], strict=True, critical_features={"score_normalized"})
    assert migrated["score_normalized"] == 0.8
    with pytest.raises(ValueError):
        migrate_feature_payload({}, FEATURE_COLUMNS_V3, strict=True, critical_features=CRITICAL_FEATURES_V3)
