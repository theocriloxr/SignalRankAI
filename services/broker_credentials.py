"""Versioned, account-bound broker credential envelopes.

New broker credentials are encrypted once at the canonical BrokerConnection
boundary.  The encrypted plaintext includes immutable ownership/context claims
so ciphertext copied to another user, connection, provider or connector fails
closed after decryption.

Environment:
    BROKER_CREDENTIAL_KEYRING_JSON
        JSON object mapping key IDs to Fernet keys, e.g.
        {"2026-q3":"<fernet-key>","2026-q2":"<previous-key>"}

    BROKER_CREDENTIAL_ACTIVE_KEY_ID
        Key ID used for all new writes/rotations.

For backwards compatibility only, when no explicit broker keyring is configured
the existing ENCRYPTION_KEY is treated as key ID "legacy-env-v1".  Existing raw
Fernet broker secrets may be read only through allow_legacy=True and should be
rotated into the bound envelope before ENCRYPTION_KEY is replaced.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from typing import Any, Mapping

from cryptography.fernet import Fernet, InvalidToken

from utils.timeutils import now_utc_naive


ENVELOPE_SCHEMA = "signalrank.broker_credential"
ENVELOPE_VERSION = 1
LEGACY_KEY_ID = "legacy-env-v1"
ENVELOPE_FORMAT = "envelope_v1"
LEGACY_FORMAT = "legacy_fernet"


class BrokerCredentialError(RuntimeError):
    """Base class for broker-credential envelope failures."""


class BrokerCredentialKeyUnavailable(BrokerCredentialError):
    """No valid active/decryption key is configured."""


class BrokerCredentialEnvelopeError(BrokerCredentialError):
    """Malformed or unsupported credential envelope."""


class BrokerCredentialBindingError(BrokerCredentialError):
    """Decrypted credentials do not belong to the requested account context."""


@dataclass(frozen=True)
class BrokerCredentialCryptoMetadata:
    format: str
    version: int
    key_id: str | None
    revision: int
    legacy: bool = False


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _utc_iso(value: datetime | None = None) -> str:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat()


def _validated_fernet(key: str, *, key_id: str) -> Fernet:
    raw = str(key or "").strip()
    if not raw:
        raise BrokerCredentialKeyUnavailable(
            f"broker credential key unavailable: {key_id}"
        )
    try:
        return Fernet(raw.encode("utf-8"))
    except Exception as exc:
        raise BrokerCredentialKeyUnavailable(
            f"broker credential key invalid: {key_id}"
        ) from exc


def _keyring(
    environ: Mapping[str, str] | None = None,
) -> tuple[dict[str, Fernet], str]:
    env = os.environ if environ is None else environ
    raw_keyring = str(env.get("BROKER_CREDENTIAL_KEYRING_JSON") or "").strip()
    active = str(env.get("BROKER_CREDENTIAL_ACTIVE_KEY_ID") or "").strip()

    if raw_keyring:
        try:
            decoded = json.loads(raw_keyring)
        except Exception as exc:
            raise BrokerCredentialKeyUnavailable(
                "BROKER_CREDENTIAL_KEYRING_JSON is invalid JSON"
            ) from exc
        if not isinstance(decoded, dict) or not decoded:
            raise BrokerCredentialKeyUnavailable(
                "BROKER_CREDENTIAL_KEYRING_JSON must be a non-empty object"
            )
        if not active:
            raise BrokerCredentialKeyUnavailable(
                "BROKER_CREDENTIAL_ACTIVE_KEY_ID is required with the keyring"
            )
        ring = {
            str(key_id): _validated_fernet(str(key), key_id=str(key_id))
            for key_id, key in decoded.items()
            if str(key_id).strip()
        }
        if active not in ring:
            raise BrokerCredentialKeyUnavailable(
                "active broker credential key is not present in the keyring"
            )
        return ring, active

    legacy_key = str(env.get("ENCRYPTION_KEY") or "").strip()
    if not legacy_key:
        raise BrokerCredentialKeyUnavailable(
            "broker credential encryption key is not configured"
        )
    return {
        LEGACY_KEY_ID: _validated_fernet(legacy_key, key_id=LEGACY_KEY_ID)
    }, LEGACY_KEY_ID


def broker_credential_encryption_available(
    environ: Mapping[str, str] | None = None,
) -> bool:
    try:
        _keyring(environ)
        return True
    except BrokerCredentialError:
        return False


def is_broker_credential_envelope(value: Any) -> bool:
    raw = str(value or "").strip()
    if not raw.startswith("{"):
        return False
    try:
        decoded = json.loads(raw)
    except Exception:
        return False
    return bool(
        isinstance(decoded, dict)
        and decoded.get("schema") == ENVELOPE_SCHEMA
        and int(decoded.get("version") or 0) == ENVELOPE_VERSION
        and str(decoded.get("ciphertext") or "").strip()
        and str(decoded.get("key_id") or "").strip()
    )


def _claims(
    *,
    user_id: int,
    connection_id: str,
    provider: str,
    connector: str,
    revision: int,
    payload: Mapping[str, Any],
    issued_at: datetime | None = None,
) -> dict[str, Any]:
    if int(user_id) <= 0:
        raise BrokerCredentialBindingError("invalid broker credential owner")
    connection = str(connection_id or "").strip()
    provider_n = _normalize(provider)
    connector_n = _normalize(connector)
    if not connection or not provider_n or not connector_n:
        raise BrokerCredentialBindingError(
            "broker credential account context is incomplete"
        )
    if int(revision) <= 0:
        raise BrokerCredentialBindingError("invalid broker credential revision")
    return {
        "schema": ENVELOPE_SCHEMA,
        "version": ENVELOPE_VERSION,
        "user_id": int(user_id),
        "connection_id": connection,
        "provider": provider_n,
        "connector": connector_n,
        "revision": int(revision),
        "issued_at": _utc_iso(issued_at),
        "payload": dict(payload),
    }


def encrypt_broker_credentials(
    payload: Mapping[str, Any],
    *,
    user_id: int,
    connection_id: str,
    provider: str,
    connector: str,
    revision: int,
    environ: Mapping[str, str] | None = None,
    issued_at: datetime | None = None,
) -> tuple[str, BrokerCredentialCryptoMetadata]:
    ring, active_key_id = _keyring(environ)
    claims = _claims(
        user_id=int(user_id),
        connection_id=connection_id,
        provider=provider,
        connector=connector,
        revision=int(revision),
        payload=payload,
        issued_at=issued_at,
    )
    plaintext = json.dumps(
        claims,
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")
    token = ring[active_key_id].encrypt(plaintext).decode("utf-8")
    envelope = {
        "schema": ENVELOPE_SCHEMA,
        "version": ENVELOPE_VERSION,
        "algorithm": "fernet",
        "key_id": active_key_id,
        "ciphertext": token,
    }
    return (
        json.dumps(envelope, separators=(",", ":"), sort_keys=True),
        BrokerCredentialCryptoMetadata(
            format=ENVELOPE_FORMAT,
            version=ENVELOPE_VERSION,
            key_id=active_key_id,
            revision=int(revision),
            legacy=False,
        ),
    )


def _parse_envelope(value: str) -> dict[str, Any]:
    try:
        envelope = json.loads(str(value or ""))
    except Exception as exc:
        raise BrokerCredentialEnvelopeError(
            "broker credential envelope is malformed"
        ) from exc
    if not isinstance(envelope, dict):
        raise BrokerCredentialEnvelopeError(
            "broker credential envelope must be an object"
        )
    if envelope.get("schema") != ENVELOPE_SCHEMA:
        raise BrokerCredentialEnvelopeError(
            "unsupported broker credential envelope schema"
        )
    if int(envelope.get("version") or 0) != ENVELOPE_VERSION:
        raise BrokerCredentialEnvelopeError(
            "unsupported broker credential envelope version"
        )
    if str(envelope.get("algorithm") or "") != "fernet":
        raise BrokerCredentialEnvelopeError(
            "unsupported broker credential envelope algorithm"
        )
    if not str(envelope.get("key_id") or "").strip():
        raise BrokerCredentialEnvelopeError(
            "broker credential envelope key ID is missing"
        )
    if not str(envelope.get("ciphertext") or "").strip():
        raise BrokerCredentialEnvelopeError(
            "broker credential envelope ciphertext is missing"
        )
    return envelope


def _decrypt_with_ring(
    token: str,
    *,
    key_id: str | None,
    environ: Mapping[str, str] | None = None,
    allow_any_key: bool = False,
) -> tuple[bytes, str]:
    ring, _ = _keyring(environ)
    if key_id:
        fernet = ring.get(str(key_id))
        if fernet is None:
            raise BrokerCredentialKeyUnavailable(
                f"broker credential key unavailable: {key_id}"
            )
        try:
            return fernet.decrypt(token.encode("utf-8")), str(key_id)
        except InvalidToken as exc:
            raise BrokerCredentialEnvelopeError(
                "broker credential ciphertext is invalid or tampered"
            ) from exc

    if not allow_any_key:
        raise BrokerCredentialKeyUnavailable(
            "broker credential key ID is required"
        )
    for candidate_id, fernet in ring.items():
        try:
            return fernet.decrypt(token.encode("utf-8")), candidate_id
        except InvalidToken:
            continue
    raise BrokerCredentialEnvelopeError(
        "legacy broker credential ciphertext cannot be decrypted"
    )


def _verify_claims(
    claims: Mapping[str, Any],
    *,
    user_id: int,
    connection_id: str,
    provider: str,
    connector: str,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    if claims.get("schema") != ENVELOPE_SCHEMA:
        raise BrokerCredentialEnvelopeError(
            "broker credential plaintext schema is invalid"
        )
    if int(claims.get("version") or 0) != ENVELOPE_VERSION:
        raise BrokerCredentialEnvelopeError(
            "broker credential plaintext version is invalid"
        )
    expected = {
        "user_id": int(user_id),
        "connection_id": str(connection_id or "").strip(),
        "provider": _normalize(provider),
        "connector": _normalize(connector),
    }
    actual = {
        "user_id": int(claims.get("user_id") or 0),
        "connection_id": str(claims.get("connection_id") or "").strip(),
        "provider": _normalize(claims.get("provider")),
        "connector": _normalize(claims.get("connector")),
    }
    if actual != expected:
        raise BrokerCredentialBindingError(
            "broker credential envelope account binding mismatch"
        )
    revision = int(claims.get("revision") or 0)
    if revision <= 0:
        raise BrokerCredentialEnvelopeError(
            "broker credential revision is invalid"
        )
    if expected_revision is not None and revision != int(expected_revision):
        raise BrokerCredentialBindingError(
            "broker credential revision mismatch"
        )
    payload = claims.get("payload")
    if not isinstance(payload, dict):
        raise BrokerCredentialEnvelopeError(
            "broker credential payload is invalid"
        )
    return dict(payload)


def decrypt_broker_credentials(
    value: str,
    *,
    user_id: int,
    connection_id: str,
    provider: str,
    connector: str,
    expected_revision: int | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], BrokerCredentialCryptoMetadata]:
    envelope = _parse_envelope(value)
    key_id = str(envelope["key_id"])
    plaintext, used_key_id = _decrypt_with_ring(
        str(envelope["ciphertext"]),
        key_id=key_id,
        environ=environ,
    )
    try:
        claims = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise BrokerCredentialEnvelopeError(
            "broker credential plaintext is malformed"
        ) from exc
    if not isinstance(claims, dict):
        raise BrokerCredentialEnvelopeError(
            "broker credential plaintext must be an object"
        )
    payload = _verify_claims(
        claims,
        user_id=int(user_id),
        connection_id=connection_id,
        provider=provider,
        connector=connector,
        expected_revision=expected_revision,
    )
    revision = int(claims["revision"])
    return payload, BrokerCredentialCryptoMetadata(
        format=ENVELOPE_FORMAT,
        version=ENVELOPE_VERSION,
        key_id=used_key_id,
        revision=revision,
        legacy=False,
    )


def _decrypt_legacy_payload(
    token: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    plaintext, _ = _decrypt_with_ring(
        str(token or ""),
        key_id=None,
        environ=environ,
        allow_any_key=True,
    )
    try:
        decoded = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise BrokerCredentialEnvelopeError(
            "legacy broker credential payload is malformed"
        ) from exc
    if not isinstance(decoded, dict):
        raise BrokerCredentialEnvelopeError(
            "legacy broker credential payload must be an object"
        )

    # Older exchange rows encrypted API components individually and then
    # encrypted the containing JSON a second time. Normalize that shape only
    # inside the explicit compatibility bridge.
    nested = {
        "api_key_enc": "api_key",
        "api_secret_enc": "api_secret",
        "passphrase_enc": "passphrase",
    }
    for encrypted_name, plaintext_name in nested.items():
        value = str(decoded.get(encrypted_name) or "").strip()
        if not value:
            continue
        nested_plaintext, _ = _decrypt_with_ring(
            value,
            key_id=None,
            environ=environ,
            allow_any_key=True,
        )
        decoded[plaintext_name] = nested_plaintext.decode("utf-8")
    return decoded


def decrypt_connection_credentials(
    row: Any,
    *,
    allow_legacy: bool = False,
    environ: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], BrokerCredentialCryptoMetadata]:
    value = str(getattr(row, "secret_encrypted", "") or "").strip()
    if not value:
        raise BrokerCredentialEnvelopeError(
            "broker connection has no application-managed credentials"
        )

    if is_broker_credential_envelope(value):
        return decrypt_broker_credentials(
            value,
            user_id=int(getattr(row, "user_id")),
            connection_id=str(getattr(row, "connection_id")),
            provider=str(getattr(row, "platform")),
            connector=str(getattr(row, "connector")),
            expected_revision=(
                int(getattr(row, "credential_revision", 0) or 0) or None
            ),
            environ=environ,
        )

    if not allow_legacy:
        raise BrokerCredentialEnvelopeError(
            "legacy broker credential format is not accepted here"
        )
    payload = _decrypt_legacy_payload(value, environ=environ)
    return payload, BrokerCredentialCryptoMetadata(
        format=LEGACY_FORMAT,
        version=0,
        key_id=None,
        revision=int(getattr(row, "credential_revision", 0) or 0),
        legacy=True,
    )


async def rotate_connection_credentials(
    *,
    user_id: int,
    connection_id: str,
    actor_user_id: int | None = None,
) -> dict[str, Any]:
    """Re-encrypt one owned connection with the active key and bound envelope."""
    from sqlalchemy import select

    from db.models import AdminEvent, BrokerConnection, User
    from db.session import get_session

    async with get_session(
        label="broker.credentials.rotate",
        timeout_seconds=10.0,
    ) as session:
        row = (
            await session.execute(
                select(BrokerConnection)
                .where(
                    BrokerConnection.user_id == int(user_id),
                    BrokerConnection.connection_id == str(connection_id),
                )
                .with_for_update()
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            raise LookupError("broker_connection_not_found")
        if not row.secret_encrypted:
            raise BrokerCredentialEnvelopeError(
                "broker connection has no application-managed credentials"
            )

        payload, previous = decrypt_connection_credentials(
            row,
            allow_legacy=True,
        )
        next_revision = max(
            1,
            int(getattr(row, "credential_revision", 0) or 0) + 1,
        )
        envelope, metadata = encrypt_broker_credentials(
            payload,
            user_id=int(row.user_id),
            connection_id=str(row.connection_id),
            provider=str(row.platform),
            connector=str(row.connector),
            revision=next_revision,
        )
        row.secret_encrypted = envelope
        row.credential_format = metadata.format
        row.credential_version = metadata.version
        row.credential_key_id = metadata.key_id
        row.credential_revision = metadata.revision
        row.credential_rotated_at = now_utc_naive()
        row.execution_enabled = False
        row.updated_at = now_utc_naive()

        actor_id = int(actor_user_id or user_id)
        actor = await session.get(User, actor_id)
        session.add(
            AdminEvent(
                event_type="broker_credentials_rotated",
                actor_telegram_user_id=(
                    int(actor.telegram_user_id)
                    if actor is not None and actor.telegram_user_id is not None
                    else None
                ),
                details={
                    "user_id": int(user_id),
                    "connection_id": str(connection_id),
                    "provider": str(row.platform),
                    "previous_format": previous.format,
                    "previous_key_id": previous.key_id,
                    "credential_revision": int(metadata.revision),
                    "credential_key_id": metadata.key_id,
                    "execution_disabled": True,
                },
                created_at=now_utc_naive(),
            )
        )
        await session.commit()
        return {
            "connection_id": str(connection_id),
            "credential_format": metadata.format,
            "credential_version": metadata.version,
            "credential_revision": metadata.revision,
            "credential_rotated_at": row.credential_rotated_at,
            "execution_enabled": False,
        }


__all__ = [
    "BrokerCredentialBindingError",
    "BrokerCredentialCryptoMetadata",
    "BrokerCredentialEnvelopeError",
    "BrokerCredentialError",
    "BrokerCredentialKeyUnavailable",
    "ENVELOPE_FORMAT",
    "ENVELOPE_SCHEMA",
    "ENVELOPE_VERSION",
    "LEGACY_FORMAT",
    "broker_credential_encryption_available",
    "decrypt_broker_credentials",
    "decrypt_connection_credentials",
    "encrypt_broker_credentials",
    "is_broker_credential_envelope",
    "rotate_connection_credentials",
]
