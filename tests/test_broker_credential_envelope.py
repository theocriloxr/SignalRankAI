from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from services.broker_connections import public_connection
from services.broker_credentials import (
    BrokerCredentialBindingError,
    BrokerCredentialEnvelopeError,
    BrokerCredentialKeyUnavailable,
    ENVELOPE_FORMAT,
    LEGACY_FORMAT,
    broker_credential_encryption_available,
    decrypt_broker_credentials,
    decrypt_connection_credentials,
    encrypt_broker_credentials,
    is_broker_credential_envelope,
)


def make_key() -> str:
    return Fernet.generate_key().decode("ascii")


def make_env(key_id: str = "current", key: str | None = None) -> dict[str, str]:
    material = key or make_key()
    return {
        "BROKER_CREDENTIAL_KEYRING_JSON": json.dumps({key_id: material}),
        "BROKER_CREDENTIAL_ACTIVE_KEY_ID": key_id,
    }


def test_bound_envelope_round_trip() -> None:
    env = make_env()
    value, metadata = encrypt_broker_credentials(
        {"username": "demo-user", "password": "demo-value", "sandbox": True},
        user_id=11,
        connection_id="conn-1",
        provider="bybit",
        connector="bybit",
        revision=1,
        environ=env,
    )
    assert is_broker_credential_envelope(value)
    assert "demo-value" not in value
    assert metadata.format == ENVELOPE_FORMAT
    assert metadata.key_id == "current"

    payload, decoded = decrypt_broker_credentials(
        value,
        user_id=11,
        connection_id="conn-1",
        provider="bybit",
        connector="bybit",
        expected_revision=1,
        environ=env,
    )
    assert payload["username"] == "demo-user"
    assert payload["password"] == "demo-value"
    assert decoded.revision == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("user_id", 12),
        ("connection_id", "conn-2"),
        ("provider", "mt5"),
        ("connector", "metaapi"),
    ],
)
def test_envelope_rejects_context_replay(field: str, value: object) -> None:
    env = make_env()
    encrypted, _ = encrypt_broker_credentials(
        {"value": "synthetic"},
        user_id=11,
        connection_id="conn-1",
        provider="bybit",
        connector="bybit",
        revision=3,
        environ=env,
    )
    kwargs = {
        "user_id": 11,
        "connection_id": "conn-1",
        "provider": "bybit",
        "connector": "bybit",
        "expected_revision": 3,
        "environ": env,
    }
    kwargs[field] = value
    with pytest.raises(BrokerCredentialBindingError):
        decrypt_broker_credentials(encrypted, **kwargs)


def test_keyring_reads_previous_key_and_writes_current_key() -> None:
    old_key = make_key()
    new_key = make_key()
    old_env = {
        "BROKER_CREDENTIAL_KEYRING_JSON": json.dumps({"old": old_key}),
        "BROKER_CREDENTIAL_ACTIVE_KEY_ID": "old",
    }
    rotated_env = {
        "BROKER_CREDENTIAL_KEYRING_JSON": json.dumps(
            {"old": old_key, "new": new_key}
        ),
        "BROKER_CREDENTIAL_ACTIVE_KEY_ID": "new",
    }
    old_value, old_meta = encrypt_broker_credentials(
        {"value": "synthetic"},
        user_id=8,
        connection_id="conn-keyring",
        provider="bybit",
        connector="bybit",
        revision=1,
        environ=old_env,
    )
    assert old_meta.key_id == "old"

    payload, read_meta = decrypt_broker_credentials(
        old_value,
        user_id=8,
        connection_id="conn-keyring",
        provider="bybit",
        connector="bybit",
        expected_revision=1,
        environ=rotated_env,
    )
    assert payload["value"] == "synthetic"
    assert read_meta.key_id == "old"

    new_value, new_meta = encrypt_broker_credentials(
        payload,
        user_id=8,
        connection_id="conn-keyring",
        provider="bybit",
        connector="bybit",
        revision=2,
        environ=rotated_env,
    )
    assert new_meta.key_id == "new"
    assert new_value != old_value
    with pytest.raises(BrokerCredentialKeyUnavailable):
        decrypt_broker_credentials(
            new_value,
            user_id=8,
            connection_id="conn-keyring",
            provider="bybit",
            connector="bybit",
            expected_revision=2,
            environ=old_env,
        )


def test_missing_key_fails_closed() -> None:
    assert broker_credential_encryption_available({}) is False
    with pytest.raises(BrokerCredentialKeyUnavailable):
        encrypt_broker_credentials(
            {"value": "synthetic"},
            user_id=1,
            connection_id="conn-1",
            provider="mt5",
            connector="metaapi",
            revision=1,
            environ={},
        )


def test_legacy_raw_token_is_explicit_compatibility_only() -> None:
    key = make_key()
    fernet = Fernet(key.encode("ascii"))
    raw = fernet.encrypt(
        json.dumps({"platform": "mt5", "login": "100", "password": "synthetic"}).encode()
    ).decode("ascii")
    row = SimpleNamespace(
        secret_encrypted=raw,
        user_id=4,
        connection_id="legacy-connection",
        platform="mt5",
        connector="metaapi",
        credential_revision=0,
    )
    env = {"ENCRYPTION_KEY": key}

    with pytest.raises(BrokerCredentialEnvelopeError, match="legacy"):
        decrypt_connection_credentials(row, allow_legacy=False, environ=env)

    payload, metadata = decrypt_connection_credentials(
        row,
        allow_legacy=True,
        environ=env,
    )
    assert payload["login"] == "100"
    assert payload["password"] == "synthetic"
    assert metadata.format == LEGACY_FORMAT


def test_public_connection_never_exposes_ciphertext_or_key_id() -> None:
    public = public_connection(
        {
            "connection_id": "conn-1",
            "platform": "bybit",
            "connector": "bybit",
            "account_ref": "12345678",
            "environment": "demo",
            "auth_mode": "api_key",
            "secret_encrypted": "opaque-ciphertext",
            "credential_format": "envelope_v1",
            "credential_version": 1,
            "credential_key_id": "key-id",
            "credential_revision": 2,
            "credential_rotated_at": None,
            "permissions": {},
            "capabilities": {},
            "execution_enabled": False,
            "is_default": False,
            "meta": {"account_classification": "DEMO"},
        }
    )
    assert public["credential_encrypted"] is True
    assert "secret_encrypted" not in public
    assert "credential_key_id" not in public
    assert "opaque-ciphertext" not in json.dumps(public)


def test_canonical_writer_and_0044_schema_contract() -> None:
    writer = Path("services/broker_connections.py").read_text(encoding="utf-8")
    migration = Path(
        "db/migrations/versions/0044_broker_credential_envelope.py"
    ).read_text(encoding="utf-8")

    assert "credential_payload" in writer
    assert "is_broker_credential_envelope(candidate)" in writer
    assert "Raw legacy broker ciphertext cannot be written" in writer
    assert "row.execution_enabled = False" in writer

    assert 'down_revision = "0043_account_execution_policy"' in migration
    for column in (
        "credential_format",
        "credential_version",
        "credential_key_id",
        "credential_revision",
        "credential_rotated_at",
    ):
        assert column in migration
    assert "legacy_fernet" in migration
    assert "secret_encrypted IS NOT NULL" in migration
    assert "decrypt_secret(" not in migration
    assert "Fernet(" not in migration


def test_0045_retires_duplicate_mt5_password_storage() -> None:
    migration = Path(
        "db/migrations/versions/0045_mt5_credential_retirement.py"
    ).read_text(encoding="utf-8")
    model = Path("db/models.py").read_text(encoding="utf-8")
    mt5 = Path("services/mt5_client.py").read_text(encoding="utf-8")

    assert 'revision = "0045_mt5_credential_retirement"' in migration
    assert 'down_revision = "0044_broker_credential_envelope"' in migration
    assert '"password_encrypted",' in migration
    assert "nullable=True" in migration
    assert "UPDATE mt5_credentials AS legacy" in migration
    assert "canonical.credential_format = 'envelope_v1'" in migration
    assert "password_encrypted = NULL" in migration
    assert "decrypt_secret(" not in migration

    assert "password_encrypted: Mapped[Optional[str]]" in model

    compatibility = mt5[
        mt5.index("async def _sync_mt5_compatibility_metadata"):
        mt5.index("# ---------------------------------------------------------------------------\n# Credential management"),
    ]
    assert "VALUES(:uid,:login,NULL,:server,:account_id,NOW(),NOW())" in compatibility
    assert "password_encrypted=NULL" in compatibility
    assert ":pw" not in compatibility
    assert "encrypt_secret" not in compatibility

    telegram_link = mt5[
        mt5.index("async def link_mt5_account("):
        mt5.index("async def get_user_mt5_account_id"),
    ]
    platform_link = mt5[
        mt5.index("async def link_platform_mt5_account("):
        mt5.index("async def get_platform_mt5_account_id"),
    ]
    canonical_link = mt5[
        mt5.index("async def link_platform_metatrader_account("):
        mt5.index("async def create_platform_metatrader_secure_link"),
    ]

    assert "link_platform_mt5_account(" in telegram_link
    assert "INSERT INTO mt5_credentials" not in telegram_link
    assert "encrypt_secret" not in telegram_link

    assert "link_platform_metatrader_account(" in platform_link
    assert "INSERT INTO mt5_credentials" not in platform_link
    assert "encrypt_secret" not in platform_link

    assert "_sync_mt5_compatibility_metadata(" in canonical_link
    assert "legacy_pw =" not in canonical_link
    assert "password_encrypted=EXCLUDED.password_encrypted" not in canonical_link
