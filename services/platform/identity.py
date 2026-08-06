"""Canonical user identity, Telegram linking and secure app sessions.

The module intentionally uses only Python's standard cryptographic primitives
plus SQLAlchemy. Passwords use scrypt with per-password salts. Access tokens are
short-lived HMAC-signed JWT-compatible compact tokens; refresh tokens are
opaque, single-use values stored only as SHA-256 hashes.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping
from urllib.parse import parse_qsl, quote
from uuid import uuid4

from sqlalchemy import text

from utils.timeutils import now_utc_naive
from services.security import decrypt_secret, encrypt_secret, is_encryption_available

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PASSWORD_PREFIX = "scrypt"
_LOCAL_AUTH_SECRET = secrets.token_bytes(32)


class AuthenticationError(ValueError):
    """Authentication failed without revealing whether an account exists."""


class IdentityConflict(ValueError):
    """The requested identity already belongs to another canonical account."""


@dataclass(frozen=True, slots=True)
class SessionTokens:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    session_id: str


@dataclass(frozen=True, slots=True)
class TelegramActivation:
    token: str
    code: str
    expires_at: datetime
    user_id: int


@dataclass(frozen=True, slots=True)
class TelegramLinkRequest:
    token: str
    code: str
    expires_at: datetime
    user_id: int


@dataclass(frozen=True, slots=True)
class TelegramLinkResult:
    status: str
    user_id: int
    existing_user_id: int | None = None
    merge_id: str | None = None


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    encoded = str(value or "")
    if not encoded or not re.fullmatch(r"[A-Za-z0-9_-]+", encoded):
        raise ValueError("invalid_base64url")
    decoded = base64.b64decode(
        encoded + "=" * (-len(encoded) % 4),
        altchars=b"-_",
        validate=True,
    )
    # Reject alternate encodings whose unused trailing bits decode to the same
    # bytes. Compact tokens must have one canonical Base64URL representation.
    if _b64encode(decoded) != encoded:
        raise ValueError("non_canonical_base64url")
    return decoded


def _sha256(value: str | bytes) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def _auth_secret() -> bytes:
    secret = str(os.getenv("APP_AUTH_SECRET") or os.getenv("WEB_SECRET_KEY") or "").strip()
    environment = str(os.getenv("ENVIRONMENT") or os.getenv("RAILWAY_ENVIRONMENT_NAME") or "local").lower()
    if not secret:
        if environment in {"production", "staging"}:
            raise RuntimeError("APP_AUTH_SECRET is required in staging and production")
        return _LOCAL_AUTH_SECRET
    if len(secret) < 32 and environment in {"production", "staging"}:
        raise RuntimeError("APP_AUTH_SECRET must contain at least 32 characters")
    return secret.encode("utf-8")


def canonical_email(email: str) -> str:
    value = str(email or "").strip().lower()
    if len(value) > 320 or not _EMAIL_RE.fullmatch(value):
        raise ValueError("invalid_email")
    return value


def validate_password(password: str) -> None:
    value = str(password or "")
    if len(value) < 10:
        raise ValueError("password_too_short")
    if len(value) > 256:
        raise ValueError("password_too_long")
    categories = sum(
        bool(pattern.search(value))
        for pattern in (re.compile(r"[a-z]"), re.compile(r"[A-Z]"), re.compile(r"\d"), re.compile(r"[^A-Za-z0-9]"))
    )
    if categories < 3:
        raise ValueError("password_requires_three_character_categories")


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    n, r, p = 2**14, 8, 1
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32)
    return f"{_PASSWORD_PREFIX}${n}${r}${p}${_b64encode(salt)}${_b64encode(derived)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        prefix, n, r, p, salt, expected = str(encoded).split("$", 5)
        if prefix != _PASSWORD_PREFIX:
            return False
        actual = hashlib.scrypt(
            str(password).encode("utf-8"),
            salt=_b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(_b64decode(expected)),
        )
        return hmac.compare_digest(actual, _b64decode(expected))
    except (ValueError, TypeError):
        return False


def encode_access_token(user_id: int, *, ttl_minutes: int | None = None, session_id: str | None = None) -> str:
    now = int(time.time())
    ttl = max(2, int(ttl_minutes or os.getenv("APP_ACCESS_TOKEN_TTL_MINUTES", "15")))
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(int(user_id)),
        "iat": now,
        "exp": now + ttl * 60,
        "jti": secrets.token_urlsafe(12),
        "typ": "access",
    }
    if session_id:
        payload["sid"] = str(session_id)
    signing_input = f"{_b64encode(json.dumps(header, separators=(',', ':')).encode())}.{_b64encode(json.dumps(payload, separators=(',', ':')).encode())}"
    signature = hmac.new(_auth_secret(), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64encode(signature)}"


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = str(token).split(".", 2)
        signing_input = f"{header_b64}.{payload_b64}"
        expected = hmac.new(_auth_secret(), signing_input.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64decode(signature_b64)):
            raise AuthenticationError("invalid_token")
        header = json.loads(_b64decode(header_b64))
        payload = json.loads(_b64decode(payload_b64))
        if header.get("alg") != "HS256" or payload.get("typ") != "access":
            raise AuthenticationError("invalid_token")
        if int(payload.get("exp", 0)) <= int(time.time()):
            raise AuthenticationError("token_expired")
        payload["user_id"] = int(payload["sub"])
        return payload
    except AuthenticationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AuthenticationError("invalid_token") from exc


def _fingerprint(value: str | None) -> str | None:
    value = str(value or "").strip()
    return _sha256(value) if value else None


async def record_security_event(
    session: Any,
    *,
    user_id: int | None,
    event_type: str,
    severity: str = "info",
    session_id: str | None = None,
    device_id: str | None = None,
    ip_address: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    await session.execute(
        text(
            "INSERT INTO security_events(user_id,event_type,severity,session_id,device_id,ip_hash,metadata) "
            "VALUES(:uid,:etype,:severity,:sid,:did,:ip,CAST(:metadata AS JSONB))"
        ),
        {
            "uid": user_id,
            "etype": str(event_type)[:64],
            "severity": str(severity)[:16],
            "sid": session_id,
            "did": device_id,
            "ip": _fingerprint(ip_address),
            "metadata": json.dumps(dict(metadata or {}), separators=(",", ":"), default=str),
        },
    )


async def ensure_telegram_user(
    session: Any,
    *,
    telegram_user_id: int,
    username: str | None = None,
    display_name: str | None = None,
) -> int:
    row = (
        await session.execute(
            text("SELECT id FROM users WHERE telegram_user_id=:telegram_id"),
            {"telegram_id": int(telegram_user_id)},
        )
    ).first()
    if row:
        user_id = int(row[0])
        await session.execute(
            text(
                "UPDATE users SET username=COALESCE(:username,username), "
                "display_name=COALESCE(:display_name,display_name), "
                "telegram_reachable=TRUE, telegram_unreachable_reason=NULL, "
                "telegram_unreachable_at=NULL, notification_suppressed=FALSE, "
                "last_active_at=NOW(), updated_at=NOW(), "
                "public_user_id=COALESCE(public_user_id, gen_random_uuid()::text) "
                "WHERE id=:uid"
            ),
            {"uid": user_id, "username": username, "display_name": display_name},
        )
    else:
        user_id = int(
            (
                await session.execute(
                    text(
                        "INSERT INTO users(telegram_user_id,username,tier,display_name,public_user_id,created_at,last_active_at,updated_at) "
                        "VALUES(:telegram_id,:username,'free',:display_name,gen_random_uuid()::text,NOW(),NOW(),NOW()) RETURNING id"
                    ),
                    {"telegram_id": int(telegram_user_id), "username": username, "display_name": display_name},
                )
            ).scalar_one()
        )
    await session.execute(
        text(
            "INSERT INTO auth_identities(identity_id,user_id,provider,provider_subject_id,verified,verified_at,metadata) "
            "VALUES(gen_random_uuid()::text,:uid,'telegram',:subject,TRUE,NOW(),CAST(:metadata AS JSONB)) "
            "ON CONFLICT(provider,provider_subject_id) DO UPDATE SET last_used_at=NOW(), disabled_at=NULL"
        ),
        {"uid": user_id, "subject": str(int(telegram_user_id)), "metadata": json.dumps({"username": username}, separators=(",", ":"))},
    )
    return user_id


async def create_email_account(session: Any, *, email: str, password: str, display_name: str | None = None) -> int:
    email_value = canonical_email(email)
    password_hash = hash_password(password)
    existing = (
        await session.execute(text("SELECT id FROM users WHERE LOWER(primary_email)=:email"), {"email": email_value})
    ).first()
    if existing:
        raise IdentityConflict("email_already_registered")
    user_id = int(
        (
            await session.execute(
                text(
                    "INSERT INTO users(telegram_user_id,username,tier,primary_email,display_name,public_user_id,account_status,onboarding_status,created_at,updated_at) "
                    "VALUES(NULL,NULL,'free',:email,:display_name,gen_random_uuid()::text,'active','started',NOW(),NOW()) RETURNING id"
                ),
                {"email": email_value, "display_name": (display_name or email_value.split('@')[0])[:160]},
            )
        ).scalar_one()
    )
    await session.execute(
        text(
            "INSERT INTO auth_identities(identity_id,user_id,provider,provider_subject_id,verified,metadata) "
            "VALUES(gen_random_uuid()::text,:uid,'email_password',:subject,FALSE,'{}'::jsonb)"
        ),
        {"uid": user_id, "subject": email_value},
    )
    await session.execute(
        text("INSERT INTO password_credentials(user_id,password_hash) VALUES(:uid,:password_hash)"),
        {"uid": user_id, "password_hash": password_hash},
    )
    await session.execute(
        text("INSERT INTO notification_preferences(user_id,telegram_enabled,email_enabled) VALUES(:uid,FALSE,FALSE) ON CONFLICT(user_id) DO NOTHING"),
        {"uid": user_id},
    )
    await record_security_event(session, user_id=user_id, event_type="account.created", metadata={"method": "email_password"})
    return user_id


async def authenticate_email_password(session: Any, *, email: str, password: str) -> int:
    email_value = canonical_email(email)
    row = (
        await session.execute(
            text(
                "SELECT u.id, p.password_hash, u.account_status "
                "FROM users u JOIN password_credentials p ON p.user_id=u.id "
                "WHERE LOWER(u.primary_email)=:email"
            ),
            {"email": email_value},
        )
    ).first()
    if not row or not verify_password(password, str(row[1])):
        raise AuthenticationError("invalid_credentials")
    if str(row[2] or "active") != "active":
        raise AuthenticationError("account_unavailable")
    await session.execute(text("UPDATE users SET last_active_at=NOW(),updated_at=NOW() WHERE id=:uid"), {"uid": int(row[0])})
    return int(row[0])


async def create_session_tokens(
    session: Any,
    *,
    user_id: int,
    user_agent: str | None = None,
    ip_address: str | None = None,
    device_id: str | None = None,
) -> SessionTokens:
    session_id = str(uuid4())
    family_id = str(uuid4())
    raw_refresh = "srr_" + secrets.token_urlsafe(48)
    now = now_utc_naive()
    refresh_expires = now + timedelta(days=max(1, int(os.getenv("APP_REFRESH_TOKEN_TTL_DAYS", "30"))))
    access_expires = now + timedelta(minutes=max(2, int(os.getenv("APP_ACCESS_TOKEN_TTL_MINUTES", "15"))))
    await session.execute(
        text(
            "INSERT INTO user_sessions(session_id,user_id,refresh_token_hash,session_family_id,device_id,user_agent_hash,ip_hash,expires_at) "
            "VALUES(:sid,:uid,:token_hash,:family,:device,:ua,:ip,:expires)"
        ),
        {
            "sid": session_id,
            "uid": int(user_id),
            "token_hash": _sha256(raw_refresh),
            "family": family_id,
            "device": device_id,
            "ua": _fingerprint(user_agent),
            "ip": _fingerprint(ip_address),
            "expires": refresh_expires,
        },
    )
    await record_security_event(
        session,
        user_id=int(user_id),
        event_type="session.created",
        session_id=session_id,
        device_id=device_id,
        ip_address=ip_address,
    )
    return SessionTokens(
        access_token=encode_access_token(int(user_id), session_id=session_id),
        refresh_token=raw_refresh,
        access_expires_at=access_expires,
        refresh_expires_at=refresh_expires,
        session_id=session_id,
    )


async def rotate_refresh_token(
    session: Any,
    *,
    refresh_token: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> SessionTokens:
    token_hash = _sha256(refresh_token)
    row = (
        await session.execute(
            text(
                "SELECT session_id,user_id,session_family_id,device_id,revoked_at,expires_at,rotated_to_session_id "
                "FROM user_sessions WHERE refresh_token_hash=:token_hash FOR UPDATE"
            ),
            {"token_hash": token_hash},
        )
    ).first()
    if not row:
        raise AuthenticationError("invalid_refresh_token")
    old_session_id, user_id, family_id, device_id, revoked_at, expires_at, rotated_to = row
    now = now_utc_naive()
    if revoked_at is not None:
        if rotated_to:
            await session.execute(
                text(
                    "UPDATE user_sessions SET revoked_at=COALESCE(revoked_at,NOW()), revoke_reason='refresh_reuse_detected', refresh_reuse_detected=TRUE "
                    "WHERE session_family_id=:family"
                ),
                {"family": family_id},
            )
            await record_security_event(
                session,
                user_id=int(user_id),
                event_type="session.refresh_reuse_detected",
                severity="critical",
                session_id=str(old_session_id),
                ip_address=ip_address,
            )
        raise AuthenticationError("refresh_token_revoked")
    if expires_at <= now:
        await session.execute(
            text("UPDATE user_sessions SET revoked_at=NOW(),revoke_reason='expired' WHERE session_id=:sid"),
            {"sid": old_session_id},
        )
        raise AuthenticationError("refresh_token_expired")

    new_session_id = str(uuid4())
    raw_refresh = "srr_" + secrets.token_urlsafe(48)
    refresh_expires = now + timedelta(days=max(1, int(os.getenv("APP_REFRESH_TOKEN_TTL_DAYS", "30"))))
    await session.execute(
        text(
            "INSERT INTO user_sessions(session_id,user_id,refresh_token_hash,session_family_id,device_id,user_agent_hash,ip_hash,expires_at) "
            "VALUES(:sid,:uid,:token_hash,:family,:device,:ua,:ip,:expires)"
        ),
        {
            "sid": new_session_id,
            "uid": int(user_id),
            "token_hash": _sha256(raw_refresh),
            "family": family_id,
            "device": device_id,
            "ua": _fingerprint(user_agent),
            "ip": _fingerprint(ip_address),
            "expires": refresh_expires,
        },
    )
    await session.execute(
        text(
            "UPDATE user_sessions SET revoked_at=NOW(),revoke_reason='rotated',rotated_to_session_id=:new_sid,last_used_at=NOW() "
            "WHERE session_id=:old_sid"
        ),
        {"new_sid": new_session_id, "old_sid": old_session_id},
    )
    access_expires = now + timedelta(minutes=max(2, int(os.getenv("APP_ACCESS_TOKEN_TTL_MINUTES", "15"))))
    return SessionTokens(
        access_token=encode_access_token(int(user_id), session_id=new_session_id),
        refresh_token=raw_refresh,
        access_expires_at=access_expires,
        refresh_expires_at=refresh_expires,
        session_id=new_session_id,
    )


async def revoke_session(session: Any, *, session_id: str, user_id: int, reason: str = "user_logout") -> bool:
    result = await session.execute(
        text(
            "UPDATE user_sessions SET revoked_at=COALESCE(revoked_at,NOW()),revoke_reason=:reason "
            "WHERE session_id=:sid AND user_id=:uid"
        ),
        {"sid": str(session_id), "uid": int(user_id), "reason": str(reason)[:128]},
    )
    return bool(result.rowcount)


async def revoke_all_sessions(session: Any, *, user_id: int, except_session_id: str | None = None) -> int:
    result = await session.execute(
        text(
            "UPDATE user_sessions SET revoked_at=COALESCE(revoked_at,NOW()),revoke_reason='logout_all' "
            "WHERE user_id=:uid AND revoked_at IS NULL AND (:except_sid IS NULL OR session_id<>:except_sid)"
        ),
        {"uid": int(user_id), "except_sid": except_session_id},
    )
    return int(result.rowcount or 0)


async def create_telegram_activation(
    session: Any,
    *,
    telegram_user_id: int,
    username: str | None = None,
    display_name: str | None = None,
) -> TelegramActivation:
    user_id = await ensure_telegram_user(
        session,
        telegram_user_id=int(telegram_user_id),
        username=username,
        display_name=display_name,
    )
    token = "sra_" + secrets.token_urlsafe(40)
    code = f"{secrets.randbelow(100_000_000):08d}"
    expires = now_utc_naive() + timedelta(minutes=max(2, int(os.getenv("APP_ACTIVATION_TTL_MINUTES", "10"))))
    await session.execute(
        text(
            "UPDATE login_challenges SET consumed_at=COALESCE(consumed_at,NOW()) "
            "WHERE user_id=:uid AND purpose='telegram_app_activation' AND consumed_at IS NULL"
        ),
        {"uid": user_id},
    )
    await session.execute(
        text(
            "INSERT INTO login_challenges(challenge_id,user_id,purpose,token_hash,code_hash,environment,expires_at,metadata) "
            "VALUES(gen_random_uuid()::text,:uid,'telegram_app_activation',:token_hash,:code_hash,:env,:expires,CAST(:metadata AS JSONB))"
        ),
        {
            "uid": user_id,
            "token_hash": _sha256(token),
            "code_hash": _sha256(code),
            "env": str(os.getenv("ENVIRONMENT") or os.getenv("RAILWAY_ENVIRONMENT_NAME") or "local")[:24],
            "expires": expires,
            "metadata": json.dumps({"telegram_user_id": int(telegram_user_id), "username": username}, separators=(",", ":")),
        },
    )
    await record_security_event(session, user_id=user_id, event_type="telegram.app_activation_created")
    return TelegramActivation(token=token, code=code, expires_at=expires, user_id=user_id)


async def complete_telegram_activation(
    session: Any,
    *,
    token_or_code: str,
    email: str,
    password: str,
    ip_address: str | None = None,
) -> int:
    credential = str(token_or_code or "").strip()
    token_hash = _sha256(credential)
    row = (
        await session.execute(
            text(
                "SELECT challenge_id,user_id,attempts,max_attempts,expires_at,consumed_at "
                "FROM login_challenges WHERE purpose='telegram_app_activation' "
                "AND (token_hash=:hash OR code_hash=:hash) ORDER BY created_at DESC LIMIT 1 FOR UPDATE"
            ),
            {"hash": token_hash},
        )
    ).first()
    if not row:
        raise AuthenticationError("invalid_activation")
    challenge_id, user_id, attempts, max_attempts, expires_at, consumed_at = row
    if consumed_at is not None:
        raise AuthenticationError("activation_already_used")
    if expires_at <= now_utc_naive():
        raise AuthenticationError("activation_expired")
    if int(attempts or 0) >= int(max_attempts or 5):
        raise AuthenticationError("activation_locked")

    email_value = canonical_email(email)
    password_hash = hash_password(password)
    conflict = (
        await session.execute(
            text("SELECT id FROM users WHERE LOWER(primary_email)=:email AND id<>:uid"),
            {"email": email_value, "uid": int(user_id)},
        )
    ).first()
    if conflict:
        raise IdentityConflict("email_belongs_to_another_account")

    await session.execute(
        text(
            "UPDATE login_challenges SET consumed_at=NOW(),consumed_ip_hash=:ip WHERE challenge_id=:cid"
        ),
        {"cid": challenge_id, "ip": _fingerprint(ip_address)},
    )
    await session.execute(
        text(
            "UPDATE users SET primary_email=:email,onboarding_status='completed',last_active_at=NOW(),updated_at=NOW() WHERE id=:uid"
        ),
        {"email": email_value, "uid": int(user_id)},
    )
    await session.execute(
        text(
            "INSERT INTO auth_identities(identity_id,user_id,provider,provider_subject_id,verified,verified_at,metadata) "
            "VALUES(gen_random_uuid()::text,:uid,'email_password',:email,TRUE,NOW(),'{}'::jsonb) "
            "ON CONFLICT(provider,provider_subject_id) DO UPDATE SET user_id=EXCLUDED.user_id,verified=TRUE,verified_at=NOW(),disabled_at=NULL"
        ),
        {"uid": int(user_id), "email": email_value},
    )
    await session.execute(
        text(
            "INSERT INTO password_credentials(user_id,password_hash) VALUES(:uid,:password_hash) "
            "ON CONFLICT(user_id) DO UPDATE SET password_hash=EXCLUDED.password_hash,password_version=password_credentials.password_version+1,updated_at=NOW(),changed_at=NOW()"
        ),
        {"uid": int(user_id), "password_hash": password_hash},
    )
    await record_security_event(
        session,
        user_id=int(user_id),
        event_type="telegram.app_activation_completed",
        ip_address=ip_address,
    )
    return int(user_id)



async def create_telegram_link_request(session: Any, *, user_id: int) -> TelegramLinkRequest:
    """Create a single-use code for linking an app account from Telegram."""
    row = (
        await session.execute(
            text("SELECT id,account_status FROM users WHERE id=:uid FOR UPDATE"),
            {"uid": int(user_id)},
        )
    ).first()
    if not row or str(row[1] or "active") != "active":
        raise AuthenticationError("account_unavailable")
    token = "srl_" + secrets.token_urlsafe(40)
    code = secrets.token_hex(5).upper()
    expires = now_utc_naive() + timedelta(minutes=max(2, int(os.getenv("APP_LINK_TTL_MINUTES", "10"))))
    await session.execute(
        text(
            "UPDATE account_link_requests SET status='superseded',completed_at=NOW() "
            "WHERE requesting_user_id=:uid AND provider='telegram' AND status='pending'"
        ),
        {"uid": int(user_id)},
    )
    await session.execute(
        text(
            "INSERT INTO account_link_requests("
            "link_id,requesting_user_id,provider,token_hash,status,expires_at,metadata"
            ") VALUES(gen_random_uuid()::text,:uid,'telegram',:token_hash,'pending',:expires,CAST(:metadata AS JSONB))"
        ),
        {
            "uid": int(user_id),
            "token_hash": _sha256(token),
            "expires": expires,
            "metadata": json.dumps({"code_hash": _sha256(code), "purpose": "app_to_telegram"}, separators=(",", ":")),
        },
    )
    await record_security_event(session, user_id=int(user_id), event_type="telegram.link_requested")
    return TelegramLinkRequest(token=token, code=code, expires_at=expires, user_id=int(user_id))


async def complete_telegram_link_request(
    session: Any,
    *,
    token_or_code: str,
    telegram_user_id: int,
    username: str | None = None,
    display_name: str | None = None,
) -> TelegramLinkResult:
    """Attach a Telegram identity to an app account or open a reviewed merge.

    The one-time code proves possession of the authenticated app session and the
    command proves possession of the Telegram identity. Existing legacy bot
    accounts are never destructively auto-merged; a reviewed merge record is
    created so subscription, delivery, paper and referral history cannot be lost.
    """
    credential = str(token_or_code or "").strip()
    if not credential:
        raise AuthenticationError("invalid_link_code")
    credential_hash = _sha256(credential)
    row = (
        await session.execute(
            text(
                "SELECT link_id,requesting_user_id,expires_at,status,metadata "
                "FROM account_link_requests WHERE provider='telegram' AND status='pending' "
                "AND (token_hash=:hash OR metadata->>'code_hash'=:hash) "
                "ORDER BY created_at DESC LIMIT 1 FOR UPDATE"
            ),
            {"hash": credential_hash},
        )
    ).first()
    if not row:
        raise AuthenticationError("invalid_link_code")
    link_id, target_user_id, expires_at, status, metadata = row
    if str(status) != "pending":
        raise AuthenticationError("link_code_already_used")
    if expires_at <= now_utc_naive():
        await session.execute(
            text("UPDATE account_link_requests SET status='expired',completed_at=NOW() WHERE link_id=:link_id"),
            {"link_id": link_id},
        )
        raise AuthenticationError("link_code_expired")

    telegram_subject = str(int(telegram_user_id))
    existing_identity = (
        await session.execute(
            text(
                "SELECT ai.user_id FROM auth_identities ai "
                "WHERE ai.provider='telegram' AND ai.provider_subject_id=:subject AND ai.disabled_at IS NULL "
                "FOR UPDATE"
            ),
            {"subject": telegram_subject},
        )
    ).first()
    existing_user_id = int(existing_identity[0]) if existing_identity else None
    if existing_user_id is None:
        legacy_row = (
            await session.execute(
                text("SELECT id FROM users WHERE telegram_user_id=:telegram_id FOR UPDATE"),
                {"telegram_id": int(telegram_user_id)},
            )
        ).first()
        existing_user_id = int(legacy_row[0]) if legacy_row else None

    target = (
        await session.execute(
            text("SELECT telegram_user_id,account_status FROM users WHERE id=:uid FOR UPDATE"),
            {"uid": int(target_user_id)},
        )
    ).first()
    if not target or str(target[1] or "active") != "active":
        raise AuthenticationError("account_unavailable")
    target_telegram = int(target[0]) if target[0] is not None else None
    if target_telegram not in {None, int(telegram_user_id)}:
        await session.execute(
            text(
                "UPDATE account_link_requests SET status='conflict',provider_subject_id=:subject,completed_at=NOW(),"
                "metadata=metadata || CAST(:metadata AS JSONB) WHERE link_id=:link_id"
            ),
            {
                "link_id": link_id,
                "subject": telegram_subject,
                "metadata": json.dumps({"reason": "target_has_other_telegram"}, separators=(",", ":")),
            },
        )
        raise IdentityConflict("account_already_has_telegram")

    if existing_user_id is not None and existing_user_id != int(target_user_id):
        merge_id = str(uuid4())
        await session.execute(
            text(
                "INSERT INTO account_merge_records(merge_id,canonical_user_id,merged_user_id,status,evidence,created_by) "
                "VALUES(:merge_id,:canonical,:merged,'pending_review',CAST(:evidence AS JSONB),:created_by) "
                "ON CONFLICT(merged_user_id) DO UPDATE SET status='pending_review',"
                "canonical_user_id=EXCLUDED.canonical_user_id,evidence=EXCLUDED.evidence,created_by=EXCLUDED.created_by"
            ),
            {
                "merge_id": merge_id,
                "canonical": int(target_user_id),
                "merged": existing_user_id,
                "created_by": int(target_user_id),
                "evidence": json.dumps(
                    {
                        "app_session_confirmed": True,
                        "telegram_command_confirmed": True,
                        "telegram_user_id": int(telegram_user_id),
                        "link_id": str(link_id),
                    },
                    separators=(",", ":"),
                ),
            },
        )
        await session.execute(
            text(
                "UPDATE account_link_requests SET status='merge_review',provider_subject_id=:subject,completed_at=NOW(),"
                "metadata=metadata || CAST(:metadata AS JSONB) WHERE link_id=:link_id"
            ),
            {
                "link_id": link_id,
                "subject": telegram_subject,
                "metadata": json.dumps({"existing_user_id": existing_user_id, "merge_id": merge_id}, separators=(",", ":")),
            },
        )
        await record_security_event(
            session,
            user_id=int(target_user_id),
            event_type="telegram.link_merge_review_required",
            severity="warning",
            metadata={"existing_user_id": existing_user_id, "merge_id": merge_id},
        )
        return TelegramLinkResult(
            status="merge_review_required",
            user_id=int(target_user_id),
            existing_user_id=existing_user_id,
            merge_id=merge_id,
        )

    await session.execute(
        text(
            "UPDATE users SET telegram_user_id=:telegram_id,username=COALESCE(:username,username),"
            "display_name=COALESCE(display_name,:display_name),telegram_reachable=TRUE,"
            "telegram_unreachable_reason=NULL,telegram_unreachable_at=NULL,notification_suppressed=FALSE,"
            "last_active_at=NOW(),updated_at=NOW() WHERE id=:uid"
        ),
        {
            "uid": int(target_user_id),
            "telegram_id": int(telegram_user_id),
            "username": username,
            "display_name": display_name,
        },
    )
    await session.execute(
        text(
            "INSERT INTO auth_identities(identity_id,user_id,provider,provider_subject_id,verified,verified_at,metadata) "
            "VALUES(gen_random_uuid()::text,:uid,'telegram',:subject,TRUE,NOW(),CAST(:metadata AS JSONB)) "
            "ON CONFLICT(provider,provider_subject_id) DO UPDATE SET user_id=EXCLUDED.user_id,verified=TRUE,"
            "verified_at=NOW(),last_used_at=NOW(),disabled_at=NULL,metadata=EXCLUDED.metadata"
        ),
        {
            "uid": int(target_user_id),
            "subject": telegram_subject,
            "metadata": json.dumps({"username": username, "linked_via": "one_time_code"}, separators=(",", ":")),
        },
    )
    await session.execute(
        text(
            "INSERT INTO notification_preferences(user_id,telegram_enabled) VALUES(:uid,TRUE) "
            "ON CONFLICT(user_id) DO UPDATE SET telegram_enabled=TRUE,updated_at=NOW()"
        ),
        {"uid": int(target_user_id)},
    )
    await session.execute(
        text(
            "UPDATE account_link_requests SET status='completed',provider_subject_id=:subject,completed_at=NOW() "
            "WHERE link_id=:link_id"
        ),
        {"link_id": link_id, "subject": telegram_subject},
    )
    await record_security_event(
        session,
        user_id=int(target_user_id),
        event_type="telegram.identity_linked",
        metadata={"telegram_user_id": int(telegram_user_id)},
    )
    return TelegramLinkResult(status="linked", user_id=int(target_user_id))

def validate_telegram_login_payload(payload: Mapping[str, Any], bot_token: str, *, max_age_seconds: int = 600) -> dict[str, Any]:
    """Validate Telegram Login Widget authorization data."""
    data = {str(k): v for k, v in payload.items() if k not in {"hash", "signature"} and v is not None}
    supplied_hash = str(payload.get("hash") or "")
    data_check = "\n".join(f"{key}={data[key]}" for key in sorted(data))
    secret_key = hashlib.sha256(str(bot_token).encode("utf-8")).digest()
    expected = hmac.new(secret_key, data_check.encode("utf-8"), hashlib.sha256).hexdigest()
    if not supplied_hash or not hmac.compare_digest(expected, supplied_hash):
        raise AuthenticationError("invalid_telegram_signature")
    auth_date = int(data.get("auth_date") or 0)
    if abs(int(time.time()) - auth_date) > max(30, int(max_age_seconds)):
        raise AuthenticationError("stale_telegram_login")
    return data


def validate_telegram_mini_app_init_data(init_data: str, bot_token: str, *, max_age_seconds: int = 600) -> dict[str, Any]:
    """Validate Telegram Mini App ``initData`` using Telegram's WebAppData key."""
    values = dict(parse_qsl(str(init_data), keep_blank_values=True))
    supplied_hash = values.pop("hash", "")
    values.pop("signature", None)
    data_check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret_key = hmac.new(b"WebAppData", str(bot_token).encode("utf-8"), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check.encode("utf-8"), hashlib.sha256).hexdigest()
    if not supplied_hash or not hmac.compare_digest(expected, supplied_hash):
        raise AuthenticationError("invalid_telegram_mini_app_signature")
    auth_date = int(values.get("auth_date") or 0)
    if abs(int(time.time()) - auth_date) > max(30, int(max_age_seconds)):
        raise AuthenticationError("stale_telegram_mini_app_data")
    if "user" in values:
        values["user"] = json.loads(values["user"])
    return values


async def user_snapshot(session: Any, user_id: int) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                "SELECT id,public_user_id,telegram_user_id,username,tier,primary_email,email_verified_at,display_name,country,timezone,locale,preferred_currency,account_status,onboarding_status,premium_until,max_risk_percentage,max_daily_drawdown_pct,risk_profile,marketing_consent,terms_version,terms_accepted_at,created_at,last_active_at "
                "FROM users WHERE id=:uid"
            ),
            {"uid": int(user_id)},
        )
    ).mappings().first()
    return dict(row) if row else None


@dataclass(frozen=True, slots=True)
class AccountChallenge:
    token: str
    expires_at: datetime
    user_id: int | None
    purpose: str


@dataclass(frozen=True, slots=True)
class MFASetup:
    secret: str
    provisioning_uri: str
    expires_at: datetime


def _totp_code(secret: str, *, at_time: int | None = None, step_seconds: int = 30, digits: int = 6) -> tuple[str, int]:
    try:
        key = base64.b32decode(str(secret).upper() + "=" * (-len(str(secret)) % 8), casefold=True)
    except Exception as exc:  # noqa: BLE001
        raise AuthenticationError("invalid_mfa_secret") from exc
    counter = int((at_time or int(time.time())) // step_seconds)
    digest = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF) % (10 ** digits)
    return str(value).zfill(digits), counter


def verify_totp(secret: str, code: str, *, window: int = 1, last_used_step: int | None = None) -> int:
    supplied = re.sub(r"\s+", "", str(code or ""))
    if not re.fullmatch(r"\d{6}", supplied):
        raise AuthenticationError("invalid_mfa_code")
    now = int(time.time())
    for delta in range(-abs(int(window)), abs(int(window)) + 1):
        expected, step = _totp_code(secret, at_time=now + delta * 30)
        if hmac.compare_digest(expected, supplied):
            if last_used_step is not None and step <= int(last_used_step):
                raise AuthenticationError("mfa_code_reused")
            return step
    raise AuthenticationError("invalid_mfa_code")


async def _create_account_challenge(
    session: Any,
    *,
    purpose: str,
    user_id: int | None,
    ttl_minutes: int,
    metadata: Mapping[str, Any] | None = None,
) -> AccountChallenge:
    token = "src_" + secrets.token_urlsafe(42)
    expires_at = now_utc_naive() + timedelta(minutes=max(2, min(int(ttl_minutes), 1440)))
    await session.execute(
        text(
            "INSERT INTO login_challenges(challenge_id,user_id,purpose,token_hash,environment,metadata,expires_at) "
            "VALUES(gen_random_uuid()::text,:uid,:purpose,:token_hash,:environment,CAST(:metadata AS JSONB),:expires)"
        ),
        {
            "uid": user_id,
            "purpose": str(purpose)[:48],
            "token_hash": _sha256(token),
            "environment": str(os.getenv("ENVIRONMENT") or os.getenv("RAILWAY_ENVIRONMENT_NAME") or "local")[:24],
            "metadata": json.dumps(dict(metadata or {}), separators=(",", ":"), default=str),
            "expires": expires_at,
        },
    )
    return AccountChallenge(token=token, expires_at=expires_at, user_id=user_id, purpose=purpose)


async def _consume_account_challenge(
    session: Any,
    *,
    token: str,
    purpose: str,
    ip_address: str | None = None,
) -> tuple[int | None, dict[str, Any]]:
    row = (
        await session.execute(
            text(
                "SELECT challenge_id,user_id,expires_at,consumed_at,attempts,max_attempts,metadata "
                "FROM login_challenges WHERE token_hash=:token_hash AND purpose=:purpose FOR UPDATE"
            ),
            {"token_hash": _sha256(str(token)), "purpose": str(purpose)},
        )
    ).mappings().first()
    if not row:
        raise AuthenticationError("invalid_or_expired_challenge")
    if row["consumed_at"] is not None:
        raise AuthenticationError("challenge_already_used")
    if row["expires_at"] <= now_utc_naive():
        raise AuthenticationError("challenge_expired")
    if int(row["attempts"] or 0) >= int(row["max_attempts"] or 5):
        raise AuthenticationError("challenge_attempt_limit")
    await session.execute(
        text(
            "UPDATE login_challenges SET consumed_at=NOW(),consumed_ip_hash=:ip WHERE challenge_id=:challenge_id"
        ),
        {"challenge_id": row["challenge_id"], "ip": _fingerprint(ip_address)},
    )
    return (int(row["user_id"]) if row["user_id"] is not None else None, dict(row["metadata"] or {}))


async def request_email_verification(session: Any, *, user_id: int, base_url: str) -> AccountChallenge:
    row = (await session.execute(text("SELECT primary_email,email_verified_at FROM users WHERE id=:uid"), {"uid": int(user_id)})).first()
    if not row or not row[0]:
        raise AuthenticationError("email_required")
    if row[1] is not None:
        raise AuthenticationError("email_already_verified")
    challenge = await _create_account_challenge(session, purpose="verify_email", user_id=int(user_id), ttl_minutes=30)
    from services.platform.email_delivery import queue_account_email
    link = f"{str(base_url).rstrip('/')}/app?verify_email={quote(challenge.token)}"
    await queue_account_email(
        session, recipient=str(row[0]), template="verify_email", user_id=int(user_id),
        context={"link": link, "expires_minutes": 30},
        idempotency_key=f"verify-email:{user_id}:{_sha256(challenge.token)[:16]}",
    )
    return challenge


async def verify_email_challenge(session: Any, *, token: str, ip_address: str | None = None) -> int:
    user_id, _ = await _consume_account_challenge(session, token=token, purpose="verify_email", ip_address=ip_address)
    if user_id is None:
        raise AuthenticationError("invalid_or_expired_challenge")
    await session.execute(
        text("UPDATE users SET email_verified_at=NOW(),updated_at=NOW() WHERE id=:uid"),
        {"uid": int(user_id)},
    )
    await session.execute(
        text(
            "UPDATE auth_identities SET verified=TRUE,verified_at=NOW(),last_used_at=NOW() "
            "WHERE user_id=:uid AND provider='email_password'"
        ),
        {"uid": int(user_id)},
    )
    await record_security_event(session, user_id=int(user_id), event_type="email.verified", ip_address=ip_address)
    return int(user_id)


async def request_magic_login(session: Any, *, email: str, base_url: str) -> AccountChallenge | None:
    value = canonical_email(email)
    row = (await session.execute(text("SELECT id FROM users WHERE LOWER(primary_email)=:email AND account_status='active'"), {"email": value})).first()
    if not row:
        return None
    user_id = int(row[0])
    challenge = await _create_account_challenge(session, purpose="magic_login", user_id=user_id, ttl_minutes=15)
    from services.platform.email_delivery import queue_account_email
    link = f"{str(base_url).rstrip('/')}/app?magic_login={quote(challenge.token)}"
    await queue_account_email(
        session, recipient=value, template="magic_login", user_id=user_id,
        context={"link": link, "expires_minutes": 15},
        idempotency_key=f"magic-login:{user_id}:{_sha256(challenge.token)[:16]}",
    )
    return challenge


async def consume_magic_login(session: Any, *, token: str, ip_address: str | None = None) -> int:
    user_id, _ = await _consume_account_challenge(session, token=token, purpose="magic_login", ip_address=ip_address)
    if user_id is None:
        raise AuthenticationError("invalid_or_expired_challenge")
    await record_security_event(session, user_id=int(user_id), event_type="session.magic_login", ip_address=ip_address)
    return int(user_id)


async def request_password_reset(session: Any, *, email: str, base_url: str) -> AccountChallenge | None:
    value = canonical_email(email)
    row = (await session.execute(text("SELECT id FROM users WHERE LOWER(primary_email)=:email AND account_status='active'"), {"email": value})).first()
    if not row:
        return None
    user_id = int(row[0])
    challenge = await _create_account_challenge(session, purpose="password_reset", user_id=user_id, ttl_minutes=20)
    from services.platform.email_delivery import queue_account_email
    link = f"{str(base_url).rstrip('/')}/app?password_reset={quote(challenge.token)}"
    await queue_account_email(
        session, recipient=value, template="password_reset", user_id=user_id,
        context={"link": link, "expires_minutes": 20},
        idempotency_key=f"password-reset:{user_id}:{_sha256(challenge.token)[:16]}",
    )
    await record_security_event(session, user_id=user_id, event_type="password.reset_requested")
    return challenge


async def complete_password_reset(
    session: Any, *, token: str, new_password: str, ip_address: str | None = None
) -> int:
    user_id, _ = await _consume_account_challenge(session, token=token, purpose="password_reset", ip_address=ip_address)
    if user_id is None:
        raise AuthenticationError("invalid_or_expired_challenge")
    password_hash = hash_password(new_password)
    await session.execute(
        text(
            "INSERT INTO password_credentials(user_id,password_hash,password_version,changed_at,updated_at) "
            "VALUES(:uid,:password_hash,1,NOW(),NOW()) ON CONFLICT(user_id) DO UPDATE SET "
            "password_hash=EXCLUDED.password_hash,password_version=password_credentials.password_version+1,"
            "changed_at=NOW(),updated_at=NOW(),compromised_at=NULL"
        ),
        {"uid": int(user_id), "password_hash": password_hash},
    )
    await revoke_all_sessions(session, user_id=int(user_id))
    await record_security_event(session, user_id=int(user_id), event_type="password.reset_completed", severity="warning", ip_address=ip_address)
    return int(user_id)


async def mfa_status(session: Any, *, user_id: int) -> dict[str, Any]:
    row = (await session.execute(text("SELECT enabled,verified_at FROM user_mfa_totp WHERE user_id=:uid"), {"uid": int(user_id)})).first()
    unused = int((await session.execute(text("SELECT COUNT(*) FROM account_recovery_codes WHERE user_id=:uid AND used_at IS NULL"), {"uid": int(user_id)})).scalar_one())
    return {"enabled": bool(row and row[0]), "verified_at": row[1] if row else None, "unused_recovery_codes": unused}


async def begin_totp_setup(session: Any, *, user_id: int, account_label: str) -> MFASetup:
    if not is_encryption_available():
        raise RuntimeError("ENCRYPTION_KEY is required for MFA")
    secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
    encrypted = encrypt_secret(secret)
    if not encrypted:
        raise RuntimeError("MFA secret encryption unavailable")
    expires_at = now_utc_naive() + timedelta(minutes=10)
    await session.execute(
        text(
            "INSERT INTO user_mfa_totp(user_id,encrypted_secret,enabled,created_at,updated_at) "
            "VALUES(:uid,:secret,FALSE,NOW(),NOW()) ON CONFLICT(user_id) DO UPDATE SET "
            "encrypted_secret=EXCLUDED.encrypted_secret,enabled=FALSE,verified_at=NULL,last_used_step=NULL,created_at=NOW(),updated_at=NOW()"
        ),
        {"uid": int(user_id), "secret": encrypted},
    )
    issuer = str(os.getenv("APP_NAME") or "SignalRankAI")
    uri = f"otpauth://totp/{quote(issuer)}:{quote(account_label)}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    await record_security_event(session, user_id=int(user_id), event_type="mfa.setup_started")
    return MFASetup(secret=secret, provisioning_uri=uri, expires_at=expires_at)


async def enable_totp(session: Any, *, user_id: int, code: str) -> list[str]:
    row = (await session.execute(text("SELECT encrypted_secret,last_used_step FROM user_mfa_totp WHERE user_id=:uid AND created_at>NOW()-INTERVAL '15 minutes' FOR UPDATE"), {"uid": int(user_id)})).first()
    if not row:
        raise AuthenticationError("mfa_setup_not_started")
    secret = decrypt_secret(str(row[0]))
    if not secret:
        raise AuthenticationError("mfa_secret_unavailable")
    step = verify_totp(secret, code, last_used_step=row[1])
    recovery_codes = [secrets.token_hex(5).upper() for _ in range(10)]
    await session.execute(text("DELETE FROM account_recovery_codes WHERE user_id=:uid"), {"uid": int(user_id)})
    for recovery in recovery_codes:
        await session.execute(
            text("INSERT INTO account_recovery_codes(recovery_code_id,user_id,code_hash) VALUES(gen_random_uuid()::text,:uid,:code_hash)"),
            {"uid": int(user_id), "code_hash": _sha256(recovery)},
        )
    await session.execute(
        text("UPDATE user_mfa_totp SET enabled=TRUE,verified_at=NOW(),last_used_step=:step,updated_at=NOW() WHERE user_id=:uid"),
        {"uid": int(user_id), "step": step},
    )
    await record_security_event(session, user_id=int(user_id), event_type="mfa.enabled", severity="warning")
    return recovery_codes


async def verify_user_mfa(session: Any, *, user_id: int, code: str) -> str:
    row = (await session.execute(text("SELECT encrypted_secret,last_used_step,enabled FROM user_mfa_totp WHERE user_id=:uid FOR UPDATE"), {"uid": int(user_id)})).first()
    supplied = re.sub(r"[^A-Za-z0-9]", "", str(code or "")).upper()
    if row and bool(row[2]) and re.fullmatch(r"\d{6}", supplied):
        secret = decrypt_secret(str(row[0]))
        if not secret:
            raise AuthenticationError("mfa_secret_unavailable")
        step = verify_totp(secret, supplied, last_used_step=row[1])
        await session.execute(text("UPDATE user_mfa_totp SET last_used_step=:step,updated_at=NOW() WHERE user_id=:uid"), {"uid": int(user_id), "step": step})
        return "totp"
    recovery = (await session.execute(text("SELECT recovery_code_id FROM account_recovery_codes WHERE user_id=:uid AND code_hash=:code_hash AND used_at IS NULL FOR UPDATE"), {"uid": int(user_id), "code_hash": _sha256(supplied)})).first()
    if recovery:
        await session.execute(text("UPDATE account_recovery_codes SET used_at=NOW() WHERE recovery_code_id=:id"), {"id": recovery[0]})
        return "recovery_code"
    raise AuthenticationError("invalid_mfa_code")


async def disable_totp(session: Any, *, user_id: int, code: str) -> None:
    await verify_user_mfa(session, user_id=int(user_id), code=code)
    await session.execute(text("DELETE FROM account_recovery_codes WHERE user_id=:uid"), {"uid": int(user_id)})
    await session.execute(text("UPDATE user_mfa_totp SET enabled=FALSE,verified_at=NULL,last_used_step=NULL,updated_at=NOW() WHERE user_id=:uid"), {"uid": int(user_id)})
    await record_security_event(session, user_id=int(user_id), event_type="mfa.disabled", severity="critical")


async def create_mfa_login_challenge(session: Any, *, user_id: int) -> AccountChallenge:
    return await _create_account_challenge(session, purpose="mfa_login", user_id=int(user_id), ttl_minutes=5)


async def complete_mfa_login(session: Any, *, token: str, code: str, ip_address: str | None = None) -> int:
    user_id, _ = await _consume_account_challenge(session, token=token, purpose="mfa_login", ip_address=ip_address)
    if user_id is None:
        raise AuthenticationError("invalid_mfa_challenge")
    method = await verify_user_mfa(session, user_id=int(user_id), code=code)
    await record_security_event(session, user_id=int(user_id), event_type="mfa.login_completed", metadata={"method": method}, ip_address=ip_address)
    return int(user_id)


__all__ = [
    "AuthenticationError",
    "IdentityConflict",
    "SessionTokens",
    "TelegramActivation",
    "TelegramLinkRequest",
    "TelegramLinkResult",
    "authenticate_email_password",
    "canonical_email",
    "complete_telegram_activation",
    "create_email_account",
    "create_session_tokens",
    "create_telegram_activation",
    "create_telegram_link_request",
    "complete_telegram_link_request",
    "decode_access_token",
    "encode_access_token",
    "ensure_telegram_user",
    "hash_password",
    "record_security_event",
    "revoke_all_sessions",
    "revoke_session",
    "rotate_refresh_token",
    "user_snapshot",
    "validate_password",
    "validate_telegram_login_payload",
    "validate_telegram_mini_app_init_data",
    "verify_password",
    "AccountChallenge",
    "MFASetup",
    "begin_totp_setup",
    "complete_mfa_login",
    "complete_password_reset",
    "consume_magic_login",
    "create_mfa_login_challenge",
    "disable_totp",
    "enable_totp",
    "mfa_status",
    "request_email_verification",
    "request_magic_login",
    "request_password_reset",
    "verify_email_challenge",
    "verify_totp",
    "verify_user_mfa",
]
