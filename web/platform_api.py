"""Unified web/mobile account and product API.

All endpoints resolve the existing ``users.id`` canonical account. Telegram,
web, mobile, subscriptions, deliveries and paper positions therefore share one
identity instead of maintaining parallel user stores.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import text

from db.session import get_session, is_db_configured
from services.security import encrypt_secret, is_encryption_available
from services.platform.webhooks import validate_webhook_destination
from core.tier_policy import evaluate_feature_access, get_entitlements, policy_snapshot
from services.platform.identity import (
    AuthenticationError,
    IdentityConflict,
    authenticate_email_password,
    begin_totp_setup,
    complete_mfa_login,
    complete_password_reset,
    complete_telegram_activation,
    consume_magic_login,
    create_email_account,
    create_mfa_login_challenge,
    create_session_tokens,
    create_telegram_link_request,
    decode_access_token,
    disable_totp,
    enable_totp,
    ensure_telegram_user,
    mfa_status,
    request_email_verification,
    request_magic_login,
    request_password_reset,
    revoke_all_sessions,
    revoke_session,
    rotate_refresh_token,
    user_snapshot,
    validate_telegram_login_payload,
    validate_telegram_mini_app_init_data,
    verify_email_challenge,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/platform", tags=["platform"])
_bearer = HTTPBearer(auto_error=False)

ACCESS_COOKIE = "sr_access"
REFRESH_COOKIE = "sr_refresh"
SESSION_COOKIE = "sr_session"
CSRF_COOKIE = "sr_csrf"


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=10, max_length=256)
    display_name: str | None = Field(default=None, max_length=160)
    client_type: str = Field(default="web", pattern=r"^(web|mobile|pwa)$")
    device_id: str | None = Field(default=None, max_length=64)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=256)
    client_type: str = Field(default="web", pattern=r"^(web|mobile|pwa)$")
    device_id: str | None = Field(default=None, max_length=64)


class RefreshRequest(BaseModel):
    refresh_token: str | None = Field(default=None, min_length=20, max_length=512)
    client_type: str = Field(default="web", pattern=r"^(web|mobile|pwa)$")


class TelegramActivationCompleteRequest(BaseModel):
    token_or_code: str = Field(min_length=6, max_length=256)
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=10, max_length=256)
    client_type: str = Field(default="web", pattern=r"^(web|mobile|pwa)$")
    device_id: str | None = Field(default=None, max_length=64)


class TelegramLoginRequest(BaseModel):
    payload: dict[str, Any]
    client_type: str = Field(default="web", pattern=r"^(web|mobile|pwa)$")
    device_id: str | None = Field(default=None, max_length=64)


class TelegramMiniAppLoginRequest(BaseModel):
    init_data: str = Field(min_length=10, max_length=8192)
    client_type: str = Field(default="web", pattern=r"^(web|mobile|pwa)$")
    device_id: str | None = Field(default=None, max_length=64)


class TelegramLinkCreateRequest(BaseModel):
    return_path: str | None = Field(default=None, max_length=256)


class PushDeviceRequest(BaseModel):
    provider: str = Field(default="expo", pattern=r"^(expo|fcm|apns)$")
    push_token: str = Field(min_length=10, max_length=512)
    platform: str = Field(pattern=r"^(android|ios|web)$")
    device_id: str | None = Field(default=None, max_length=64)
    app_version: str | None = Field(default=None, max_length=32)


class CheckoutCreateRequest(BaseModel):
    product_id: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]+$")
    currency: str = Field(default="NGN", pattern=r"^NGN$")


class WatchlistCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class WatchlistItemRequest(BaseModel):
    instrument_id: str = Field(min_length=2, max_length=128)


class NotificationPreferenceRequest(BaseModel):
    telegram_enabled: bool | None = None
    web_enabled: bool | None = None
    email_enabled: bool | None = None
    push_enabled: bool | None = None
    webhook_enabled: bool | None = None
    quiet_hours_start: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    quiet_hours_end: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str | None = Field(default=None, max_length=64)


class JournalEntryRequest(BaseModel):
    title: str | None = Field(default=None, max_length=180)
    notes: str = Field(default="", max_length=20000)
    signal_id: str | None = Field(default=None, max_length=36)
    paper_position_id: str | None = Field(default=None, max_length=36)
    emotion: str | None = Field(default=None, max_length=64)
    mistake_category: str | None = Field(default=None, max_length=96)
    plan_adherence: int | None = Field(default=None, ge=0, le=100)
    result_r: float | None = Field(default=None, ge=-1000, le=1000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    occurred_at: datetime | None = None


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=lambda: ["signals:read"], max_length=20)
    expires_in_days: int | None = Field(default=90, ge=1, le=3650)


class WebhookCreateRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    events: list[str] = Field(default_factory=lambda: ["signal.generated", "signal.closed"], max_length=30)


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    slug: str | None = Field(default=None, min_length=2, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]+$")


class SupportTicketCreateRequest(BaseModel):
    subject: str = Field(min_length=3, max_length=180)
    category: str = Field(default="general", max_length=64)
    message: str = Field(min_length=3, max_length=20000)


class SupportMessageCreateRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)


class EmailRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)


class TokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)
    client_type: str = Field(default="web", pattern=r"^(web|mobile|pwa)$")
    device_id: str | None = Field(default=None, max_length=64)


class PasswordResetCompleteRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)
    new_password: str = Field(min_length=10, max_length=256)


class MFACompleteRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)
    code: str = Field(min_length=6, max_length=32)
    client_type: str = Field(default="web", pattern=r"^(web|mobile|pwa)$")
    device_id: str | None = Field(default=None, max_length=64)


class MFACodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    country: str | None = Field(default=None, min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")
    timezone: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=16)
    preferred_currency: str | None = Field(default=None, min_length=3, max_length=8, pattern=r"^[A-Za-z0-9]+$")
    max_risk_percentage: float | None = Field(default=None, ge=0.1, le=10.0)
    max_daily_drawdown_pct: float | None = Field(default=None, ge=0.5, le=50.0)
    marketing_consent: bool | None = None


class OrganizationInviteRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    role: str = Field(default="viewer", pattern=r"^(administrator|trader|analyst|risk_manager|viewer|developer|billing|auditor)$")


class OrganizationInvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)


class AlertCreateRequest(BaseModel):
    instrument_id: str | None = Field(default=None, max_length=128)
    asset: str | None = Field(default=None, max_length=32)
    alert_type: str = Field(pattern=r"^(price_above|price_below|signal_generated|entry_triggered|outcome|provider_status)$")
    condition: dict[str, Any] = Field(default_factory=dict)
    channels: list[str] = Field(default_factory=lambda: ["telegram", "web"], max_length=5)



def _assert_feature(user: dict[str, Any], feature: str) -> None:
    decision = evaluate_feature_access(str(user.get("tier") or "free"), feature)
    if not decision.allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "code": decision.code,
                "feature": feature,
                "required_tier": decision.required_tier.value,
                "current_tier": decision.current_tier.value,
                "message": decision.reason,
            },
        )


def _normalized_scopes(values: list[str]) -> list[str]:
    allowed = {
        "signals:read", "instruments:read", "portfolio:read", "paper:read",
        "journal:read", "webhooks:write", "organization:read",
    }
    result = sorted({str(value).strip().lower() for value in values if str(value).strip().lower() in allowed})
    if not result:
        raise HTTPException(status_code=422, detail="At least one supported API scope is required")
    return result


async def professional_api_user(
    bearer: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    """Authenticate a scoped Professional API key without treating it as a web session."""
    raw = str(getattr(bearer, "credentials", "") or "")
    if not raw.startswith("srk_"):
        raise HTTPException(status_code=401, detail="Professional API key required")
    parts = raw.split("_", 2)
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="Invalid API key")
    key_prefix = "_".join(parts[:2])
    secret_hash = __import__("hashlib").sha256(raw.encode("utf-8")).hexdigest()
    async with get_session() as session:
        row = (
            await session.execute(
                text(
                    "SELECT key_id,user_id,scopes,expires_at FROM api_keys "
                    "WHERE key_prefix=:prefix AND secret_hash=:secret_hash AND active=TRUE "
                    "AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>NOW()) FOR UPDATE"
                ),
                {"prefix": key_prefix, "secret_hash": secret_hash},
            )
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid or expired API key")
        user = await user_snapshot(session, int(row["user_id"]))
        if not user:
            raise HTTPException(status_code=401, detail="Account unavailable")
        _assert_feature(user, "rest_api")
        await session.execute(
            text("UPDATE api_keys SET last_used_at=NOW() WHERE key_id=:key_id"),
            {"key_id": row["key_id"]},
        )
        await session.commit()
    user["auth_type"] = "api_key"
    user["api_key_id"] = row["key_id"]
    user["api_scopes"] = list(row["scopes"] or [])
    return user


def _require_api_scope(user: dict[str, Any], scope: str) -> None:
    scopes = {str(value) for value in (user.get("api_scopes") or [])}
    if scope not in scopes and "*" not in scopes:
        raise HTTPException(status_code=403, detail=f"API key scope required: {scope}")

def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else None


def _app_base_url(request: Request) -> str:
    configured = str(
        os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or os.getenv("APP_BASE_URL")
        or os.getenv("STAGING_APP_BASE_URL")
        or ""
    ).strip().rstrip("/")
    if configured and not configured.startswith(("http://", "https://")):
        configured = f"https://{configured}"
    return configured or str(request.base_url).rstrip("/")


def _cookie_secure() -> bool:
    raw = str(os.getenv("APP_COOKIE_SECURE", "1")).lower()
    return raw in {"1", "true", "yes", "on"}


def _set_session_cookies(response: Response, *, access: str, refresh: str, session_id: str) -> str:
    domain = str(os.getenv("APP_COOKIE_DOMAIN") or "").strip() or None
    common = {
        "httponly": True,
        "secure": _cookie_secure(),
        "samesite": "lax",
        "domain": domain,
        "path": "/",
    }
    refresh_max_age = max(86400, int(os.getenv("APP_REFRESH_TOKEN_TTL_DAYS", "30")) * 86400)
    response.set_cookie(ACCESS_COOKIE, access, max_age=max(120, int(os.getenv("APP_ACCESS_TOKEN_TTL_MINUTES", "15")) * 60), **common)
    response.set_cookie(REFRESH_COOKIE, refresh, max_age=refresh_max_age, **common)
    response.set_cookie(SESSION_COOKIE, session_id, max_age=refresh_max_age, **common)
    csrf = secrets.token_urlsafe(32)
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=refresh_max_age,
        httponly=False,
        secure=_cookie_secure(),
        samesite="lax",
        domain=domain,
        path="/",
    )
    return csrf


def _clear_session_cookies(response: Response) -> None:
    domain = str(os.getenv("APP_COOKIE_DOMAIN") or "").strip() or None
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, domain=domain, path="/")


def _token_response(tokens, client_type: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "authenticated": True,
        "session_id": tokens.session_id,
        "access_expires_at": tokens.access_expires_at.isoformat(),
        "refresh_expires_at": tokens.refresh_expires_at.isoformat(),
    }
    if client_type == "mobile":
        payload["access_token"] = tokens.access_token
        payload["refresh_token"] = tokens.refresh_token
        payload["token_type"] = "bearer"
    return payload


def _auth_token(request: Request, bearer: HTTPAuthorizationCredentials | None) -> str:
    return str((bearer.credentials if bearer else None) or request.cookies.get(ACCESS_COOKIE) or "").strip()


async def current_user(
    request: Request,
    bearer: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    token = _auth_token(request, bearer)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        claims = decode_access_token(token)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if not is_db_configured():
        raise HTTPException(status_code=503, detail="Database unavailable")
    async with get_session() as session:
        session_id = str(claims.get("sid") or "")
        active_session = None
        if session_id:
            active_session = (
                await session.execute(
                    text(
                        "SELECT 1 FROM user_sessions "
                        "WHERE session_id=:sid AND user_id=:uid AND revoked_at IS NULL AND expires_at>NOW()"
                    ),
                    {"sid": session_id, "uid": int(claims["user_id"])},
                )
            ).first()
        if not active_session:
            raise HTTPException(status_code=401, detail="Session is no longer active")
        user = await user_snapshot(session, int(claims["user_id"]))
        await session.rollback()
    if not user or str(user.get("account_status") or "active") != "active":
        raise HTTPException(status_code=401, detail="Account unavailable")
    user["session_id"] = claims.get("sid")
    return user


async def _create_login_response(
    response: Response,
    request: Request,
    *,
    user_id: int,
    client_type: str,
    device_id: str | None,
) -> dict[str, Any]:
    async with get_session() as session:
        tokens = await create_session_tokens(
            session,
            user_id=int(user_id),
            user_agent=request.headers.get("user-agent"),
            ip_address=_client_ip(request),
            device_id=device_id,
        )
        user = await user_snapshot(session, int(user_id))
        await session.commit()
    csrf = _set_session_cookies(response, access=tokens.access_token, refresh=tokens.refresh_token, session_id=tokens.session_id)
    payload = {**_token_response(tokens, client_type), "user": user}
    if client_type != "mobile":
        payload["csrf_token"] = csrf
    return payload


@router.get("/capabilities")
async def capabilities() -> dict[str, Any]:
    return {
        "account_model": "canonical_user_multi_identity",
        "login_methods": ["email_password", "email_magic_link", "telegram_activation", "telegram_login", "telegram_mini_app", "totp_mfa"],
        "planned_login_methods": ["google", "apple", "passkey", "institutional_sso"],
        "clients": ["telegram", "web", "pwa", "android", "ios", "api"],
        "live_execution_enabled": False,
    }


@router.post("/auth/register", status_code=201)
async def register(payload: RegisterRequest, request: Request, response: Response) -> dict[str, Any]:
    if not is_db_configured():
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        async with get_session() as session:
            user_id = await create_email_account(
                session,
                email=payload.email,
                password=payload.password,
                display_name=payload.display_name,
            )
            await request_email_verification(session, user_id=user_id, base_url=_app_base_url(request))
            await session.commit()
    except IdentityConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _create_login_response(
        response,
        request,
        user_id=user_id,
        client_type=payload.client_type,
        device_id=payload.device_id,
    )


@router.post("/auth/login")
async def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    try:
        async with get_session() as session:
            user_id = await authenticate_email_password(session, email=payload.email, password=payload.password)
            status = await mfa_status(session, user_id=user_id)
            if status["enabled"]:
                challenge = await create_mfa_login_challenge(session, user_id=user_id)
                await session.commit()
                return {
                    "authenticated": False,
                    "mfa_required": True,
                    "mfa_token": challenge.token,
                    "expires_at": challenge.expires_at.isoformat(),
                }
            await session.commit()
    except (AuthenticationError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid credentials") from exc
    return await _create_login_response(
        response,
        request,
        user_id=user_id,
        client_type=payload.client_type,
        device_id=payload.device_id,
    )


@router.post("/auth/refresh")
async def refresh(payload: RefreshRequest, request: Request, response: Response) -> dict[str, Any]:
    raw = str(payload.refresh_token or request.cookies.get(REFRESH_COOKIE) or "").strip()
    if not raw:
        raise HTTPException(status_code=401, detail="Refresh token required")
    try:
        async with get_session() as session:
            tokens = await rotate_refresh_token(
                session,
                refresh_token=raw,
                user_agent=request.headers.get("user-agent"),
                ip_address=_client_ip(request),
            )
            user = await user_snapshot(session, decode_access_token(tokens.access_token)["user_id"])
            await session.commit()
    except AuthenticationError as exc:
        _clear_session_cookies(response)
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    _set_session_cookies(response, access=tokens.access_token, refresh=tokens.refresh_token, session_id=tokens.session_id)
    return {**_token_response(tokens, payload.client_type), "user": user}


@router.post("/auth/telegram/complete")
async def telegram_activation_complete(
    payload: TelegramActivationCompleteRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    try:
        async with get_session() as session:
            user_id = await complete_telegram_activation(
                session,
                token_or_code=payload.token_or_code,
                email=payload.email,
                password=payload.password,
                ip_address=_client_ip(request),
            )
            await session.commit()
    except IdentityConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (AuthenticationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _create_login_response(
        response,
        request,
        user_id=user_id,
        client_type=payload.client_type,
        device_id=payload.device_id,
    )


@router.post("/auth/telegram/login")
async def telegram_login(payload: TelegramLoginRequest, request: Request, response: Response) -> dict[str, Any]:
    bot_token = str(os.getenv("TELEGRAM_BOT_TOKEN") or "")
    if not bot_token:
        raise HTTPException(status_code=503, detail="Telegram login unavailable")
    try:
        verified = validate_telegram_login_payload(payload.payload, bot_token)
        telegram_id = int(verified["id"])
        display_name = " ".join(filter(None, [verified.get("first_name"), verified.get("last_name")])).strip()
        async with get_session() as session:
            user_id = await ensure_telegram_user(
                session,
                telegram_user_id=telegram_id,
                username=verified.get("username"),
                display_name=display_name or None,
            )
            await session.commit()
    except (AuthenticationError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return await _create_login_response(
        response,
        request,
        user_id=user_id,
        client_type=payload.client_type,
        device_id=payload.device_id,
    )


@router.post("/auth/telegram/mini-app")
async def telegram_mini_app_login(
    payload: TelegramMiniAppLoginRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    bot_token = str(os.getenv("TELEGRAM_BOT_TOKEN") or "")
    if not bot_token:
        raise HTTPException(status_code=503, detail="Telegram Mini App unavailable")
    try:
        verified = validate_telegram_mini_app_init_data(payload.init_data, bot_token)
        tg_user = dict(verified.get("user") or {})
        telegram_id = int(tg_user["id"])
        display_name = " ".join(filter(None, [tg_user.get("first_name"), tg_user.get("last_name")])).strip()
        async with get_session() as session:
            user_id = await ensure_telegram_user(
                session,
                telegram_user_id=telegram_id,
                username=tg_user.get("username"),
                display_name=display_name or None,
            )
            await session.commit()
    except (AuthenticationError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return await _create_login_response(
        response,
        request,
        user_id=user_id,
        client_type=payload.client_type,
        device_id=payload.device_id,
    )


@router.post("/auth/logout")
async def logout(request: Request, response: Response, user: dict[str, Any] = Depends(current_user)) -> dict[str, bool]:
    sid = str(user.get("session_id") or request.cookies.get(SESSION_COOKIE) or "")
    if sid:
        async with get_session() as session:
            await revoke_session(session, session_id=sid, user_id=int(user["id"]))
            await session.commit()
    _clear_session_cookies(response)
    return {"logged_out": True}


@router.post("/auth/logout-all")
async def logout_all(response: Response, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    async with get_session() as session:
        count = await revoke_all_sessions(session, user_id=int(user["id"]))
        await session.commit()
    _clear_session_cookies(response)
    return {"logged_out": True, "sessions_revoked": count}


@router.get("/me")
async def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return {"user": user}


@router.get("/entitlements")
async def entitlements(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    policy = get_entitlements(str(user.get("tier") or "free"))
    return {
        "tier": policy.tier.value,
        "features": sorted(policy.features),
        "limits": {
            "daily_signals": policy.daily_signal_limit,
            "history_days": policy.history_days,
            "max_tp_levels": policy.max_tp_levels,
            "delivery_delay_minutes": policy.delivery_delay_minutes,
        },
        "policy_version": policy_snapshot()["version"],
    }


@router.get("/dashboard")
async def dashboard(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    uid = int(user["id"])
    async with get_session() as session:
        summary = (
            await session.execute(
                text(
                    "SELECT "
                    "(SELECT COUNT(*) FROM signal_deliveries WHERE user_id=:uid AND sent_ok=TRUE) AS delivered_signals, "
                    "(SELECT COUNT(*) FROM paper_positions WHERE user_id=:uid AND status='open') AS open_positions, "
                    "(SELECT COALESCE(SUM(unrealized_pnl),0) FROM paper_positions WHERE user_id=:uid AND status='open') AS unrealized_pnl, "
                    "(SELECT COALESCE(cash_balance,0) FROM paper_accounts WHERE user_id=:uid LIMIT 1) AS paper_cash, "
                    "(SELECT COUNT(*) FROM watchlists WHERE user_id=:uid) AS watchlists"
                ),
                {"uid": uid},
            )
        ).mappings().first()
        subscription = (
            await session.execute(
                text(
                    "SELECT tier,status,started_at,expires_at FROM subscriptions "
                    "WHERE user_id=:uid AND status='active' AND (expires_at IS NULL OR expires_at>NOW()) "
                    "ORDER BY started_at DESC LIMIT 1"
                ),
                {"uid": uid},
            )
        ).mappings().first()
        await session.rollback()
    return {"user": user, "summary": dict(summary or {}), "subscription": dict(subscription or {})}


@router.get("/signals")
async def signal_feed(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    asset: str | None = Query(default=None, max_length=32),
    status: str | None = Query(default=None, max_length=32),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    filters = ["d.user_id=:uid", "d.sent_ok=TRUE"]
    params: dict[str, Any] = {"uid": int(user["id"]), "limit": int(limit), "offset": int(offset)}
    if asset:
        filters.append("s.asset=:asset")
        params["asset"] = asset.upper()
    if status:
        filters.append("COALESCE(o.status,s.status)=:status")
        params["status"] = status.lower()
    sql = (
        "SELECT s.signal_id,s.display_id,s.asset,s.asset_class,s.timeframe,s.direction,s.entry,s.stop_loss,s.take_profit,"
        "s.rr_estimate,s.score,s.strategy_name,s.strategy_group,s.regime,s.created_at,s.ml_probability_calibrated,"
        "d.delivered_at,d.delivery_latency_seconds,d.signal_age_at_delivery_seconds,o.status AS outcome_status,o.r_multiple,o.pnl_pct "
        "FROM signal_deliveries d JOIN signals s ON s.signal_id=d.signal_id "
        "LEFT JOIN outcomes o ON o.signal_id=s.signal_id WHERE " + " AND ".join(filters) +
        " ORDER BY d.delivered_at DESC LIMIT :limit OFFSET :offset"
    )
    async with get_session() as session:
        rows = (await session.execute(text(sql), params)).mappings().all()
        await session.rollback()
    return {"signals": [dict(row) for row in rows], "limit": limit, "offset": offset}


@router.get("/paper")
async def paper_summary(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    uid = int(user["id"])
    async with get_session() as session:
        account = (
            await session.execute(text("SELECT * FROM paper_accounts WHERE user_id=:uid LIMIT 1"), {"uid": uid})
        ).mappings().first()
        positions = (
            await session.execute(
                text(
                    "SELECT position_id,signal_id,asset,asset_class,timeframe,direction,status,fill_entry,current_price,stop_loss,take_profits,target_price,quantity,notional,unrealized_pnl,realized_pnl,r_multiple,opened_at,closed_at,exit_reason "
                    "FROM paper_positions WHERE user_id=:uid ORDER BY opened_at DESC LIMIT 100"
                ),
                {"uid": uid},
            )
        ).mappings().all()
        await session.rollback()
    return {"account": dict(account or {}), "positions": [dict(row) for row in positions]}


@router.get("/instruments/search")
async def instrument_search(
    q: str = Query(default="", max_length=80),
    asset_class: str | None = Query(default=None, max_length=32),
    instrument_type: str | None = Query(default=None, max_length=32),
    venue: str | None = Query(default=None, max_length=64),
    limit: int = Query(30, ge=1, le=100),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    del user
    filters = ["i.active=TRUE"]
    params: dict[str, Any] = {"q": f"%{q.strip()}%", "limit": int(limit)}
    if q.strip():
        filters.append("(i.canonical_symbol ILIKE :q OR i.display_symbol ILIKE :q OR pi.provider_symbol ILIKE :q OR i.underlying ILIKE :q)")
    if asset_class:
        filters.append("i.asset_class=:asset_class")
        params["asset_class"] = asset_class.lower()
    if instrument_type:
        filters.append("i.instrument_type=:instrument_type")
        params["instrument_type"] = instrument_type.lower()
    if venue:
        filters.append("pi.venue=:venue")
        params["venue"] = venue.lower()
    sql = (
        "SELECT i.instrument_id,i.canonical_symbol,i.display_symbol,i.asset_class,i.instrument_type,i.market_type,i.base_currency,i.quote_currency,i.settlement_currency,i.underlying,i.tick_size,i.quantity_step,i.minimum_notional,i.tradable,i.discovery_status,"
        "COUNT(pi.id) AS provider_count,ARRAY_REMOVE(ARRAY_AGG(DISTINCT pi.provider),NULL) AS providers,ARRAY_REMOVE(ARRAY_AGG(DISTINCT pi.venue),NULL) AS venues "
        "FROM instruments i LEFT JOIN provider_instruments pi ON pi.canonical_instrument_id=i.instrument_id "
        "WHERE " + " AND ".join(filters) + " GROUP BY i.instrument_id ORDER BY i.tradable DESC,provider_count DESC,i.canonical_symbol LIMIT :limit"
    )
    async with get_session() as session:
        rows = (await session.execute(text(sql), params)).mappings().all()
        await session.rollback()
    return {"instruments": [dict(row) for row in rows]}


@router.get("/watchlists")
async def list_watchlists(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    async with get_session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT w.watchlist_id,w.name,w.is_default,w.created_at,w.updated_at,"
                    "COALESCE(jsonb_agg(jsonb_build_object('instrument_id',wi.instrument_id)) FILTER (WHERE wi.instrument_id IS NOT NULL),'[]'::jsonb) AS items "
                    "FROM watchlists w LEFT JOIN watchlist_items wi ON wi.watchlist_id=w.watchlist_id "
                    "WHERE w.user_id=:uid GROUP BY w.watchlist_id ORDER BY w.is_default DESC,w.created_at"
                ),
                {"uid": int(user["id"])},
            )
        ).mappings().all()
        await session.rollback()
    return {"watchlists": [dict(row) for row in rows]}


@router.post("/watchlists", status_code=201)
async def create_watchlist(payload: WatchlistCreateRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    watchlist_id = str(uuid4())
    async with get_session() as session:
        try:
            await session.execute(
                text("INSERT INTO watchlists(watchlist_id,user_id,name) VALUES(:wid,:uid,:name)"),
                {"wid": watchlist_id, "uid": int(user["id"]), "name": payload.name.strip()},
            )
            await session.commit()
        except Exception as exc:
            await session.rollback()
            raise HTTPException(status_code=409, detail="Watchlist already exists") from exc
    return {"watchlist_id": watchlist_id, "name": payload.name.strip()}


@router.post("/watchlists/{watchlist_id}/items", status_code=201)
async def add_watchlist_item(
    watchlist_id: str,
    payload: WatchlistItemRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    async with get_session() as session:
        owner = (
            await session.execute(
                text("SELECT 1 FROM watchlists WHERE watchlist_id=:wid AND user_id=:uid"),
                {"wid": watchlist_id, "uid": int(user["id"])},
            )
        ).first()
        if not owner:
            raise HTTPException(status_code=404, detail="Watchlist not found")
        instrument = (
            await session.execute(text("SELECT 1 FROM instruments WHERE instrument_id=:iid"), {"iid": payload.instrument_id})
        ).first()
        if not instrument:
            raise HTTPException(status_code=404, detail="Instrument not found")
        await session.execute(
            text("INSERT INTO watchlist_items(watchlist_id,instrument_id) VALUES(:wid,:iid) ON CONFLICT DO NOTHING"),
            {"wid": watchlist_id, "iid": payload.instrument_id},
        )
        await session.commit()
    return {"added": True}


@router.post("/account/telegram-link")
async def create_telegram_link(
    payload: TelegramLinkCreateRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    """Create a one-time Telegram deep-link for an authenticated app user."""
    async with get_session() as session:
        request = await create_telegram_link_request(session, user_id=int(user["id"]))
        await session.commit()
    username = str(os.getenv("BOT_USERNAME") or os.getenv("TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")
    deep_link = f"https://t.me/{username}?start=link_{request.code}" if username else None
    return {
        "code": request.code,
        "expires_at": request.expires_at.isoformat(),
        "telegram_deep_link": deep_link,
        "instructions": "Open the SignalRankAI bot and send /link followed by this one-time code.",
    }


@router.post("/push-devices")
async def register_push_device(payload: PushDeviceRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    token_hash = __import__("hashlib").sha256(payload.push_token.encode("utf-8")).hexdigest()
    if not is_encryption_available():
        raise HTTPException(status_code=503, detail="Push registration requires ENCRYPTION_KEY")
    encrypted_token = encrypt_secret(payload.push_token)
    if not encrypted_token:
        raise HTTPException(status_code=503, detail="Push token encryption unavailable")
    async with get_session() as session:
        await session.execute(text("""
            INSERT INTO push_devices(
              push_device_id,user_id,device_id,provider,push_token_hash,encrypted_push_token,
              platform,app_version,active,last_registered_at
            ) VALUES (
              :id,:uid,:device_id,:provider,:token_hash,:token,:platform,:app_version,TRUE,NOW()
            )
            ON CONFLICT (push_token_hash) DO UPDATE SET
              user_id=EXCLUDED.user_id,device_id=EXCLUDED.device_id,
              encrypted_push_token=EXCLUDED.encrypted_push_token,
              platform=EXCLUDED.platform,app_version=EXCLUDED.app_version,
              active=TRUE,last_registered_at=NOW(),revoked_at=NULL
        """), {
            "id": str(uuid4()), "uid": int(user["id"]), "device_id": payload.device_id,
            "provider": payload.provider, "token_hash": token_hash,
            "token": encrypted_token, "platform": payload.platform,
            "app_version": payload.app_version,
        })
        await session.commit()
    return {"registered": True, "provider": payload.provider, "platform": payload.platform}


@router.delete("/push-devices/{push_device_id}")
async def revoke_push_device(push_device_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    async with get_session() as session:
        result = await session.execute(text("""
            UPDATE push_devices SET active=FALSE,revoked_at=NOW()
            WHERE push_device_id=:id AND user_id=:uid
        """), {"id": push_device_id, "uid": int(user["id"])})
        await session.commit()
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="Push device not found")
    return {"revoked": True}


@router.get("/devices")
async def devices(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    async with get_session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT session_id,device_id,created_at,last_used_at,expires_at,revoked_at,revoke_reason "
                    "FROM user_sessions WHERE user_id=:uid ORDER BY created_at DESC LIMIT 100"
                ),
                {"uid": int(user["id"])},
            )
        ).mappings().all()
        await session.rollback()
    return {"sessions": [dict(row) for row in rows], "current_session_id": user.get("session_id")}


@router.get("/notifications/preferences")
async def get_notification_preferences(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    async with get_session() as session:
        row = (
            await session.execute(text("SELECT * FROM notification_preferences WHERE user_id=:uid"), {"uid": int(user["id"])})
        ).mappings().first()
        await session.rollback()
    return {"preferences": dict(row or {})}


@router.put("/notifications/preferences")
async def update_notification_preferences(
    payload: NotificationPreferenceRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        return await get_notification_preferences(user)
    assignments = []
    params: dict[str, Any] = {"uid": int(user["id"])}
    for key, value in fields.items():
        assignments.append(f"{key}=:{key}")
        params[key] = value
    async with get_session() as session:
        await session.execute(
            text(
                "INSERT INTO notification_preferences(user_id) VALUES(:uid) ON CONFLICT(user_id) DO NOTHING"
            ),
            {"uid": int(user["id"])},
        )
        await session.execute(
            text("UPDATE notification_preferences SET " + ",".join(assignments) + ",updated_at=NOW() WHERE user_id=:uid"),
            params,
        )
        await session.commit()
    return await get_notification_preferences(user)


@router.get("/journal")
async def journal_entries(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    async with get_session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT journal_entry_id,signal_id,paper_position_id,title,notes,emotion,mistake_category,"
                    "plan_adherence,result_r,tags,occurred_at,created_at,updated_at "
                    "FROM journal_entries WHERE user_id=:uid ORDER BY occurred_at DESC LIMIT :limit OFFSET :offset"
                ),
                {"uid": int(user["id"]), "limit": int(limit), "offset": int(offset)},
            )
        ).mappings().all()
        await session.rollback()
    return {"entries": [dict(row) for row in rows]}


@router.post("/journal", status_code=201)
async def create_journal_entry(
    payload: JournalEntryRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    entry_id = str(uuid4())
    tags = sorted({str(value).strip()[:64] for value in payload.tags if str(value).strip()})
    async with get_session() as session:
        await session.execute(
            text(
                "INSERT INTO journal_entries("
                "journal_entry_id,user_id,signal_id,paper_position_id,title,notes,emotion,mistake_category,"
                "plan_adherence,result_r,tags,occurred_at"
                ") VALUES(:entry_id,:uid,:signal_id,:position_id,:title,:notes,:emotion,:mistake,"
                ":adherence,:result_r,CAST(:tags AS JSONB),COALESCE(:occurred_at,NOW()))"
            ),
            {
                "entry_id": entry_id,
                "uid": int(user["id"]),
                "signal_id": payload.signal_id,
                "position_id": payload.paper_position_id,
                "title": payload.title,
                "notes": payload.notes,
                "emotion": payload.emotion,
                "mistake": payload.mistake_category,
                "adherence": payload.plan_adherence,
                "result_r": payload.result_r,
                "tags": json.dumps(tags, separators=(",", ":")),
                "occurred_at": payload.occurred_at,
            },
        )
        await session.commit()
    return {"journal_entry_id": entry_id, "created": True}


@router.delete("/journal/{journal_entry_id}")
async def delete_journal_entry(
    journal_entry_id: str,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    async with get_session() as session:
        result = await session.execute(
            text("DELETE FROM journal_entries WHERE journal_entry_id=:entry_id AND user_id=:uid"),
            {"entry_id": journal_entry_id, "uid": int(user["id"])},
        )
        await session.commit()
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    return {"deleted": True}


@router.get("/api-keys")
async def list_api_keys(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    _assert_feature(user, "rest_api")
    async with get_session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT key_id,name,key_prefix,scopes,active,expires_at,last_used_at,revoked_at,created_at "
                    "FROM api_keys WHERE user_id=:uid ORDER BY created_at DESC"
                ),
                {"uid": int(user["id"])},
            )
        ).mappings().all()
        await session.rollback()
    return {"api_keys": [dict(row) for row in rows]}


@router.post("/api-keys", status_code=201)
async def create_api_key(
    payload: ApiKeyCreateRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    _assert_feature(user, "rest_api")
    scopes = _normalized_scopes(payload.scopes)
    key_id = str(uuid4())
    prefix = "srk_" + key_id.replace("-", "")[:12]
    raw_key = prefix + "_" + secrets.token_urlsafe(36)
    secret_hash = __import__("hashlib").sha256(raw_key.encode("utf-8")).hexdigest()
    expires_at = datetime.utcnow() + timedelta(days=int(payload.expires_in_days)) if payload.expires_in_days else None
    async with get_session() as session:
        await session.execute(
            text(
                "INSERT INTO api_keys(key_id,user_id,name,key_prefix,secret_hash,scopes,expires_at) "
                "VALUES(:key_id,:uid,:name,:prefix,:secret_hash,CAST(:scopes AS JSONB),:expires_at)"
            ),
            {
                "key_id": key_id,
                "uid": int(user["id"]),
                "name": payload.name.strip(),
                "prefix": prefix,
                "secret_hash": secret_hash,
                "scopes": json.dumps(scopes, separators=(",", ":")),
                "expires_at": expires_at,
            },
        )
        await session.commit()
    return {
        "key_id": key_id,
        "name": payload.name.strip(),
        "api_key": raw_key,
        "prefix": prefix,
        "scopes": scopes,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "warning": "This key is shown once. Store it in a secret manager.",
    }


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(key_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    _assert_feature(user, "rest_api")
    async with get_session() as session:
        result = await session.execute(
            text(
                "UPDATE api_keys SET active=FALSE,revoked_at=NOW() "
                "WHERE key_id=:key_id AND user_id=:uid AND revoked_at IS NULL"
            ),
            {"key_id": key_id, "uid": int(user["id"])},
        )
        await session.commit()
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"revoked": True}


@router.get("/professional/signals")
async def professional_signal_feed(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: dict[str, Any] = Depends(professional_api_user),
) -> dict[str, Any]:
    _require_api_scope(user, "signals:read")
    async with get_session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT s.id AS signal_id,s.asset,s.direction,s.timeframe,s.entry,s.stop_loss,s.tp1,s.tp2,s.tp3,"
                    "s.score,s.strategy_name,s.status,s.created_at,d.sent_at AS delivered_at,o.status AS outcome_status "
                    "FROM signal_deliveries d JOIN signals s ON s.id=d.signal_id "
                    "LEFT JOIN outcomes o ON o.signal_id=s.id WHERE d.user_id=:uid AND d.sent_ok=TRUE "
                    "ORDER BY d.sent_at DESC LIMIT :limit OFFSET :offset"
                ),
                {"uid": int(user["id"]), "limit": int(limit), "offset": int(offset)},
            )
        ).mappings().all()
        await session.rollback()
    return {"signals": [dict(row) for row in rows], "api_key_id": user.get("api_key_id")}


@router.get("/webhooks")
async def list_webhooks(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    _assert_feature(user, "outbound_webhooks")
    async with get_session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT webhook_endpoint_id,url,subscribed_events,active,created_at,updated_at "
                    "FROM webhook_endpoints WHERE user_id=:uid ORDER BY created_at DESC"
                ),
                {"uid": int(user["id"])},
            )
        ).mappings().all()
        await session.rollback()
    return {"webhooks": [dict(row) for row in rows]}


@router.post("/webhooks", status_code=201)
async def create_webhook(
    payload: WebhookCreateRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    _assert_feature(user, "outbound_webhooks")
    try:
        destination = await validate_webhook_destination(payload.url.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not is_encryption_available():
        raise HTTPException(status_code=503, detail="Webhook creation requires ENCRYPTION_KEY")
    events = sorted({str(value).strip().lower()[:96] for value in payload.events if str(value).strip()})
    if not events:
        raise HTTPException(status_code=422, detail="At least one webhook event is required")
    secret = "srwh_" + secrets.token_urlsafe(40)
    encrypted = encrypt_secret(secret)
    if not encrypted:
        raise HTTPException(status_code=503, detail="Webhook secret encryption unavailable")
    endpoint_id = str(uuid4())
    async with get_session() as session:
        await session.execute(
            text(
                "INSERT INTO webhook_endpoints(webhook_endpoint_id,user_id,url,secret_hash,encrypted_secret,subscribed_events) "
                "VALUES(:endpoint_id,:uid,:url,:secret_hash,:encrypted,CAST(:events AS JSONB))"
            ),
            {
                "endpoint_id": endpoint_id,
                "uid": int(user["id"]),
                "url": destination,
                "secret_hash": __import__("hashlib").sha256(secret.encode("utf-8")).hexdigest(),
                "encrypted": encrypted,
                "events": json.dumps(events, separators=(",", ":")),
            },
        )
        await session.commit()
    return {
        "webhook_endpoint_id": endpoint_id,
        "url": destination,
        "events": events,
        "signing_secret": secret,
        "warning": "This signing secret is shown once.",
    }


@router.delete("/webhooks/{webhook_endpoint_id}")
async def revoke_webhook(
    webhook_endpoint_id: str,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    _assert_feature(user, "outbound_webhooks")
    async with get_session() as session:
        result = await session.execute(
            text(
                "UPDATE webhook_endpoints SET active=FALSE,updated_at=NOW() "
                "WHERE webhook_endpoint_id=:endpoint_id AND user_id=:uid"
            ),
            {"endpoint_id": webhook_endpoint_id, "uid": int(user["id"])},
        )
        await session.commit()
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"revoked": True}


@router.get("/organizations")
async def organizations(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    _assert_feature(user, "team_workspace")
    async with get_session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT o.organization_id,o.name,o.slug,o.tier,o.status,m.role,m.joined_at "
                    "FROM organizations o JOIN organization_members m ON m.organization_id=o.organization_id "
                    "WHERE m.user_id=:uid AND m.status='active' ORDER BY o.created_at DESC"
                ),
                {"uid": int(user["id"])},
            )
        ).mappings().all()
        await session.rollback()
    return {"organizations": [dict(row) for row in rows]}


@router.post("/organizations", status_code=201)
async def create_organization(
    payload: OrganizationCreateRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    _assert_feature(user, "team_workspace")
    slug = payload.slug or "-".join(filter(None, "".join(ch.lower() if ch.isalnum() else " " for ch in payload.name).split()))
    if len(slug) < 2:
        slug = "signalrank-team-" + secrets.token_hex(3)
    organization_id = str(uuid4())
    async with get_session() as session:
        try:
            await session.execute(
                text(
                    "INSERT INTO organizations(organization_id,name,slug,owner_user_id,tier) "
                    "VALUES(:organization_id,:name,:slug,:uid,:tier)"
                ),
                {
                    "organization_id": organization_id,
                    "name": payload.name.strip(),
                    "slug": slug[:100],
                    "uid": int(user["id"]),
                    "tier": str(user.get("tier") or "professional").lower(),
                },
            )
            await session.execute(
                text(
                    "INSERT INTO organization_members(organization_id,user_id,role,status) "
                    "VALUES(:organization_id,:uid,'owner','active')"
                ),
                {"organization_id": organization_id, "uid": int(user["id"])},
            )
            await session.commit()
        except Exception as exc:
            await session.rollback()
            raise HTTPException(status_code=409, detail="Organization slug already exists") from exc
    return {"organization_id": organization_id, "name": payload.name.strip(), "slug": slug[:100]}


@router.get("/support/tickets")
async def support_tickets(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    async with get_session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT ticket_id,subject,category,priority,status,created_at,updated_at,closed_at "
                    "FROM support_tickets WHERE user_id=:uid ORDER BY created_at DESC LIMIT 100"
                ),
                {"uid": int(user["id"])},
            )
        ).mappings().all()
        await session.rollback()
    return {"tickets": [dict(row) for row in rows]}


@router.post("/support/tickets", status_code=201)
async def create_support_ticket(
    payload: SupportTicketCreateRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    ticket_id = str(uuid4())
    message_id = str(uuid4())
    priority = "priority" if get_entitlements(str(user.get("tier") or "free")).support_level in {"priority", "professional", "dedicated"} else "normal"
    async with get_session() as session:
        await session.execute(
            text(
                "INSERT INTO support_tickets(ticket_id,user_id,subject,category,priority) "
                "VALUES(:ticket_id,:uid,:subject,:category,:priority)"
            ),
            {
                "ticket_id": ticket_id,
                "uid": int(user["id"]),
                "subject": payload.subject.strip(),
                "category": payload.category.strip().lower(),
                "priority": priority,
            },
        )
        await session.execute(
            text(
                "INSERT INTO support_messages(message_id,ticket_id,author_user_id,author_role,message) "
                "VALUES(:message_id,:ticket_id,:uid,'user',:message)"
            ),
            {
                "message_id": message_id,
                "ticket_id": ticket_id,
                "uid": int(user["id"]),
                "message": payload.message.strip(),
            },
        )
        await session.commit()
    return {"ticket_id": ticket_id, "status": "open", "priority": priority}


@router.post("/auth/mfa/complete")
async def mfa_login_complete(
    payload: MFACompleteRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    try:
        async with get_session() as session:
            user_id = await complete_mfa_login(
                session,
                token=payload.token,
                code=payload.code,
                ip_address=_client_ip(request),
            )
            await session.commit()
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return await _create_login_response(
        response,
        request,
        user_id=user_id,
        client_type=payload.client_type,
        device_id=payload.device_id,
    )


@router.post("/auth/magic-link/request", status_code=202)
async def magic_link_request(payload: EmailRequest, request: Request) -> dict[str, Any]:
    # Always return the same response to avoid account enumeration.
    try:
        async with get_session() as session:
            await request_magic_login(session, email=payload.email, base_url=_app_base_url(request))
            await session.commit()
    except ValueError:
        pass
    return {"accepted": True, "message": "If the account exists, a sign-in link has been queued."}


@router.post("/auth/magic-link/complete")
async def magic_link_complete(
    payload: TokenRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    try:
        async with get_session() as session:
            user_id = await consume_magic_login(session, token=payload.token, ip_address=_client_ip(request))
            status = await mfa_status(session, user_id=user_id)
            if status["enabled"]:
                challenge = await create_mfa_login_challenge(session, user_id=user_id)
                await session.commit()
                return {
                    "authenticated": False,
                    "mfa_required": True,
                    "mfa_token": challenge.token,
                    "expires_at": challenge.expires_at.isoformat(),
                }
            await session.commit()
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return await _create_login_response(
        response,
        request,
        user_id=user_id,
        client_type=payload.client_type,
        device_id=payload.device_id,
    )


@router.post("/auth/password-reset/request", status_code=202)
async def password_reset_request(payload: EmailRequest, request: Request) -> dict[str, Any]:
    try:
        async with get_session() as session:
            await request_password_reset(session, email=payload.email, base_url=_app_base_url(request))
            await session.commit()
    except ValueError:
        pass
    return {"accepted": True, "message": "If the account exists, reset instructions have been queued."}


@router.post("/auth/password-reset/complete")
async def password_reset_complete(payload: PasswordResetCompleteRequest, request: Request) -> dict[str, Any]:
    try:
        async with get_session() as session:
            await complete_password_reset(
                session,
                token=payload.token,
                new_password=payload.new_password,
                ip_address=_client_ip(request),
            )
            await session.commit()
    except (AuthenticationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"reset": True, "message": "Password changed. Sign in again on every device."}


@router.post("/auth/email-verification/request", status_code=202)
async def email_verification_request(
    request: Request,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    try:
        async with get_session() as session:
            await request_email_verification(session, user_id=int(user["id"]), base_url=_app_base_url(request))
            await session.commit()
    except AuthenticationError as exc:
        if str(exc) == "email_already_verified":
            return {"accepted": True, "already_verified": True}
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"accepted": True}


@router.post("/auth/email-verification/complete")
async def email_verification_complete(payload: TokenRequest, request: Request) -> dict[str, Any]:
    try:
        async with get_session() as session:
            user_id = await verify_email_challenge(session, token=payload.token, ip_address=_client_ip(request))
            await session.commit()
    except AuthenticationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"verified": True, "user_id": user_id}


@router.get("/security/mfa")
async def get_mfa_status(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    async with get_session() as session:
        status = await mfa_status(session, user_id=int(user["id"]))
        await session.rollback()
    return status


@router.post("/security/mfa/setup")
async def setup_mfa(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    async with get_session() as session:
        setup = await begin_totp_setup(
            session,
            user_id=int(user["id"]),
            account_label=str(user.get("primary_email") or user.get("public_user_id") or user["id"]),
        )
        await session.commit()
    return {"secret": setup.secret, "provisioning_uri": setup.provisioning_uri, "expires_at": setup.expires_at.isoformat()}


@router.post("/security/mfa/enable")
async def confirm_mfa(payload: MFACodeRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    try:
        async with get_session() as session:
            recovery_codes = await enable_totp(session, user_id=int(user["id"]), code=payload.code)
            await session.commit()
    except AuthenticationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"enabled": True, "recovery_codes": recovery_codes, "warning": "Store these once-only codes offline. They will not be shown again."}


@router.post("/security/mfa/disable")
async def remove_mfa(payload: MFACodeRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    try:
        async with get_session() as session:
            await disable_totp(session, user_id=int(user["id"]), code=payload.code)
            await session.commit()
    except AuthenticationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"enabled": False}


@router.patch("/profile")
async def update_profile(payload: ProfileUpdateRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    values = payload.model_dump(exclude_unset=True)
    if not values:
        return {"user": user}
    assignments: list[str] = []
    params: dict[str, Any] = {"uid": int(user["id"])}
    allowed = {
        "display_name", "timezone", "locale", "max_risk_percentage",
        "max_daily_drawdown_pct", "marketing_consent",
    }
    for key, value in values.items():
        if key not in allowed and key not in {"country", "preferred_currency"}:
            continue
        if key == "country" and value:
            value = str(value).upper()
        if key == "preferred_currency" and value:
            value = str(value).upper()
        assignments.append(f"{key}=:{key}")
        params[key] = value
    if not assignments:
        return {"user": user}
    async with get_session() as session:
        await session.execute(text("UPDATE users SET " + ",".join(assignments) + ",updated_at=NOW() WHERE id=:uid"), params)
        updated = await user_snapshot(session, int(user["id"]))
        await session.commit()
    return {"user": updated}


@router.delete("/devices/{session_id}")
async def revoke_device_session(session_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if str(session_id) == str(user.get("session_id") or ""):
        raise HTTPException(status_code=409, detail="Use logout to revoke the current session")
    async with get_session() as session:
        revoked = await revoke_session(session, session_id=session_id, user_id=int(user["id"]), reason="device_revoked")
        await session.commit()
    if not revoked:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"revoked": True}


@router.delete("/watchlists/{watchlist_id}")
async def delete_watchlist(watchlist_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    async with get_session() as session:
        result = await session.execute(
            text("DELETE FROM watchlists WHERE watchlist_id=:id AND user_id=:uid"),
            {"id": watchlist_id, "uid": int(user["id"])},
        )
        await session.commit()
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return {"deleted": True}


@router.delete("/watchlists/{watchlist_id}/items/{instrument_id}")
async def remove_watchlist_item(
    watchlist_id: str,
    instrument_id: str,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    async with get_session() as session:
        result = await session.execute(
            text(
                "DELETE FROM watchlist_items wi USING watchlists w WHERE wi.watchlist_id=w.watchlist_id "
                "AND wi.watchlist_id=:watchlist_id AND wi.instrument_id=:instrument_id AND w.user_id=:uid"
            ),
            {"watchlist_id": watchlist_id, "instrument_id": instrument_id, "uid": int(user["id"])},
        )
        await session.commit()
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    return {"deleted": True}


@router.get("/portfolio")
async def portfolio(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    uid = int(user["id"])
    async with get_session() as session:
        account = (await session.execute(text("SELECT id,cash_balance,realized_pnl,currency FROM paper_accounts WHERE user_id=:uid"), {"uid": uid})).mappings().first()
        exposures = (await session.execute(text(
            "SELECT asset,asset_class,direction,COUNT(*) AS positions,COALESCE(SUM(notional),0) AS notional,"
            "COALESCE(SUM(unrealized_pnl),0) AS unrealized_pnl FROM paper_positions "
            "WHERE user_id=:uid AND status='open' GROUP BY asset,asset_class,direction ORDER BY ABS(SUM(notional)) DESC"
        ), {"uid": uid})).mappings().all()
        equity_curve = (await session.execute(text(
            "SELECT created_at,balance_after,entry_type,amount FROM paper_ledger_entries WHERE user_id=:uid ORDER BY created_at DESC LIMIT 250"
        ), {"uid": uid})).mappings().all()
        await session.rollback()
    cash = float((account or {}).get("cash_balance") or 0)
    unrealized = sum(float(row.get("unrealized_pnl") or 0) for row in exposures)
    return {"account": dict(account or {}), "equity": cash + unrealized, "exposures": [dict(row) for row in exposures], "equity_curve": [dict(row) for row in reversed(equity_curve)]}


@router.get("/performance")
async def performance(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    uid = int(user["id"])
    async with get_session() as session:
        summary = (await session.execute(text(
            "SELECT COUNT(*) FILTER (WHERE included) AS signals,"
            "COUNT(*) FILTER (WHERE included AND primary_bucket IN ('win','tp1','tp2','tp3','partial_win','partial_win_be')) AS wins,"
            "COUNT(*) FILTER (WHERE included AND primary_bucket IN ('loss','sl')) AS losses,"
            "COALESCE(AVG(final_realized_r) FILTER (WHERE included),0) AS average_r,"
            "COALESCE(SUM(final_realized_r) FILTER (WHERE included),0) AS total_r "
            "FROM performance_ledger_entries WHERE user_id=:uid"
        ), {"uid": uid})).mappings().first()
        breakdown = (await session.execute(text(
            "SELECT asset,timeframe,COUNT(*) AS signals,COALESCE(AVG(final_realized_r),0) AS average_r,"
            "COALESCE(SUM(final_realized_r),0) AS total_r FROM performance_ledger_entries "
            "WHERE user_id=:uid AND included GROUP BY asset,timeframe ORDER BY COUNT(*) DESC LIMIT 100"
        ), {"uid": uid})).mappings().all()
        await session.rollback()
    data = dict(summary or {})
    total = int(data.get("signals") or 0)
    data["win_rate"] = (int(data.get("wins") or 0) / total) if total else None
    data["claim_certified"] = False
    data["disclaimer"] = "User-level proof-backed history; not a guaranteed future win rate."
    return {"summary": data, "breakdown": [dict(row) for row in breakdown]}


@router.get("/billing/products")
async def billing_products(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    """Return current public checkout products from the server catalogue."""
    from payments.catalog import ProductCatalogueError, resolve_checkout_product
    products: list[dict[str, Any]] = []
    async with get_session(label="platform.billing.products", timeout_seconds=10.0) as session:
        rows = (await session.execute(text(
            "SELECT product_id FROM subscription_products WHERE active=TRUE ORDER BY product_id"
        ))).all()
        for row in rows:
            try:
                product = await resolve_checkout_product(session, str(row[0]), currency="NGN")
            except ProductCatalogueError:
                continue
            products.append({
                "product_id": product.product_id,
                "tier": product.tier,
                "display_name": product.display_name,
                "duration_days": product.duration_days,
                "currency": product.currency,
                "price_ngn": product.price_ngn,
            })
        await session.rollback()
    return {"products": products}


@router.post("/billing/checkout", status_code=201)
async def create_billing_checkout(
    payload: CheckoutCreateRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    """Initialize a server-priced Paystack checkout for any canonical account."""
    uid = int(user["id"])
    async with get_session(label="platform.billing.checkout.catalog", timeout_seconds=10.0) as session:
        account = (
            await session.execute(
                text(
                    "SELECT id,primary_email,email_verified_at,telegram_user_id,account_status "
                    "FROM users WHERE id=:uid"
                ),
                {"uid": uid},
            )
        ).mappings().first()
        if not account or str(account.get("account_status") or "active") != "active":
            raise HTTPException(status_code=403, detail="Account unavailable")
        if not account.get("primary_email") or account.get("email_verified_at") is None:
            raise HTTPException(status_code=409, detail="Verify an email address before checkout")
        try:
            from payments.catalog import ProductCatalogueError, resolve_checkout_product
            product = await resolve_checkout_product(session, payload.product_id, currency=payload.currency)
        except ProductCatalogueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        await session.rollback()

    try:
        from payments.checkout import CheckoutInitializationError, initialize_paystack_checkout
        checkout = await initialize_paystack_checkout(
            product=product,
            canonical_user_id=uid,
            telegram_user_id=(int(account["telegram_user_id"]) if account.get("telegram_user_id") is not None else None),
            email=str(account["primary_email"]),
        )
    except CheckoutInitializationError as exc:
        logger.warning("[billing_checkout] user=%s product=%s blocked=%s", uid, payload.product_id, exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return checkout


@router.get("/billing")
async def billing(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    uid = int(user["id"])
    async with get_session() as session:
        subscriptions = (await session.execute(text(
            "SELECT id,tier,status,started_at,expires_at,paystack_reference,bonus_days FROM subscriptions "
            "WHERE user_id=:uid ORDER BY started_at DESC LIMIT 100"
        ), {"uid": uid})).mappings().all()
        receipts = (await session.execute(text(
            "SELECT receipt_number,provider,payment_reference,plan,amount,currency,status,payment_date,subscription_start,subscription_end "
            "FROM payment_receipts WHERE user_id=:uid ORDER BY payment_date DESC LIMIT 100"
        ), {"uid": uid})).mappings().all()
        await session.rollback()
    return {"subscriptions": [dict(row) for row in subscriptions], "receipts": [dict(row) for row in receipts]}


@router.get("/notifications")
async def notification_center(
    unread_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    condition = " AND read_at IS NULL" if unread_only else ""
    async with get_session() as session:
        rows = (await session.execute(text(
            "SELECT notification_id,event_type,title,body,severity,channel_data,read_at,created_at "
            "FROM notification_events WHERE user_id=:uid" + condition + " ORDER BY created_at DESC LIMIT :limit"
        ), {"uid": int(user["id"]), "limit": int(limit)})).mappings().all()
        await session.rollback()
    return {"notifications": [dict(row) for row in rows]}


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    async with get_session() as session:
        result = await session.execute(text(
            "UPDATE notification_events SET read_at=COALESCE(read_at,NOW()) WHERE notification_id=:id AND user_id=:uid"
        ), {"id": notification_id, "uid": int(user["id"])})
        await session.commit()
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"read": True}


async def _organization_role(session: Any, organization_id: str, user_id: int) -> str | None:
    row = (await session.execute(text(
        "SELECT role FROM organization_members WHERE organization_id=:org AND user_id=:uid AND status='active'"
    ), {"org": organization_id, "uid": int(user_id)})).first()
    return str(row[0]) if row else None


@router.get("/organizations/{organization_id}/members")
async def organization_members(organization_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    async with get_session() as session:
        role = await _organization_role(session, organization_id, int(user["id"]))
        if not role:
            raise HTTPException(status_code=404, detail="Organization not found")
        rows = (await session.execute(text(
            "SELECT m.user_id,m.role,m.status,m.joined_at,u.public_user_id,u.display_name,u.primary_email "
            "FROM organization_members m JOIN users u ON u.id=m.user_id WHERE m.organization_id=:org ORDER BY m.joined_at"
        ), {"org": organization_id})).mappings().all()
        await session.rollback()
    return {"role": role, "members": [dict(row) for row in rows]}


@router.post("/organizations/{organization_id}/invitations", status_code=201)
async def create_organization_invitation(
    organization_id: str,
    payload: OrganizationInviteRequest,
    request: Request,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    from services.platform.identity import canonical_email
    from services.platform.email_delivery import queue_account_email
    email = canonical_email(payload.email)
    token = "sri_" + secrets.token_urlsafe(40)
    token_hash = __import__("hashlib").sha256(token.encode()).hexdigest()
    invitation_id = str(uuid4())
    expires_at = datetime.utcnow() + timedelta(days=7)
    async with get_session() as session:
        role = await _organization_role(session, organization_id, int(user["id"]))
        if role not in {"owner", "administrator"}:
            raise HTTPException(status_code=403, detail="Organization administrator required")
        await session.execute(text(
            "INSERT INTO organization_invitations(invitation_id,organization_id,email,role,token_hash,invited_by,expires_at) "
            "VALUES(:id,:org,:email,:role,:token_hash,:uid,:expires)"
        ), {"id": invitation_id, "org": organization_id, "email": email, "role": payload.role, "token_hash": token_hash, "uid": int(user["id"]), "expires": expires_at})
        link = f"{_app_base_url(request)}/app?organization_invite={token}"
        await queue_account_email(session, recipient=email, template="organization_invite", context={"link": link, "expires_minutes": 10080}, idempotency_key=f"org-invite:{invitation_id}")
        await session.execute(text(
            "INSERT INTO organization_audit_events(audit_id,organization_id,actor_user_id,event_type,metadata) "
            "VALUES(gen_random_uuid()::text,:org,:uid,'member.invited',CAST(:metadata AS JSONB))"
        ), {"org": organization_id, "uid": int(user["id"]), "metadata": json.dumps({"email": email, "role": payload.role})})
        await session.commit()
    return {"invitation_id": invitation_id, "expires_at": expires_at.isoformat()}


@router.post("/organizations/invitations/accept")
async def accept_organization_invitation(
    payload: OrganizationInvitationAcceptRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    token_hash = __import__("hashlib").sha256(payload.token.encode()).hexdigest()
    async with get_session() as session:
        row = (await session.execute(text(
            "SELECT invitation_id,organization_id,email,role,status,expires_at FROM organization_invitations "
            "WHERE token_hash=:token_hash FOR UPDATE"
        ), {"token_hash": token_hash})).mappings().first()
        if not row or row["status"] != "pending" or row["expires_at"] <= datetime.utcnow():
            raise HTTPException(status_code=422, detail="Invalid or expired invitation")
        if str(user.get("primary_email") or "").lower() != str(row["email"]).lower():
            raise HTTPException(status_code=403, detail="Invitation email does not match this account")
        await session.execute(text(
            "INSERT INTO organization_members(organization_id,user_id,role,status) VALUES(:org,:uid,:role,'active') "
            "ON CONFLICT(organization_id,user_id) DO UPDATE SET role=EXCLUDED.role,status='active'"
        ), {"org": row["organization_id"], "uid": int(user["id"]), "role": row["role"]})
        await session.execute(text(
            "UPDATE organization_invitations SET status='accepted',accepted_by=:uid,accepted_at=NOW() WHERE invitation_id=:id"
        ), {"uid": int(user["id"]), "id": row["invitation_id"]})
        await session.commit()
    return {"accepted": True, "organization_id": row["organization_id"]}


@router.get("/support/tickets/{ticket_id}")
async def support_ticket_detail(ticket_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    async with get_session() as session:
        ticket = (await session.execute(text(
            "SELECT ticket_id,subject,category,priority,status,created_at,updated_at,closed_at FROM support_tickets "
            "WHERE ticket_id=:ticket_id AND user_id=:uid"
        ), {"ticket_id": ticket_id, "uid": int(user["id"])})).mappings().first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        messages = (await session.execute(text(
            "SELECT message_id,author_user_id,author_role,message,created_at FROM support_messages "
            "WHERE ticket_id=:ticket_id ORDER BY created_at"
        ), {"ticket_id": ticket_id})).mappings().all()
        await session.rollback()
    return {"ticket": dict(ticket), "messages": [dict(row) for row in messages]}


@router.post("/support/tickets/{ticket_id}/messages", status_code=201)
async def add_support_message(
    ticket_id: str,
    payload: SupportMessageCreateRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    message_id = str(uuid4())
    async with get_session() as session:
        ticket = (await session.execute(text(
            "SELECT status FROM support_tickets WHERE ticket_id=:ticket_id AND user_id=:uid FOR UPDATE"
        ), {"ticket_id": ticket_id, "uid": int(user["id"])})).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if str(ticket[0]) == "closed":
            raise HTTPException(status_code=409, detail="Ticket is closed")
        await session.execute(text(
            "INSERT INTO support_messages(message_id,ticket_id,author_user_id,author_role,message) "
            "VALUES(:message_id,:ticket_id,:uid,'user',:message)"
        ), {"message_id": message_id, "ticket_id": ticket_id, "uid": int(user["id"]), "message": payload.message.strip()})
        await session.execute(text("UPDATE support_tickets SET updated_at=NOW() WHERE ticket_id=:ticket_id"), {"ticket_id": ticket_id})
        await session.commit()
    return {"message_id": message_id}


@router.get("/alerts")
async def list_alerts(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    async with get_session() as session:
        rows = (await session.execute(text(
            "SELECT alert_id,instrument_id,asset,alert_type,condition,channels,active,last_triggered_at,created_at "
            "FROM user_alerts WHERE user_id=:uid ORDER BY created_at DESC"
        ), {"uid": int(user["id"])})).mappings().all()
        await session.rollback()
    return {"alerts": [dict(row) for row in rows]}


@router.post("/alerts", status_code=201)
async def create_alert(payload: AlertCreateRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    channels = sorted({str(channel).lower() for channel in payload.channels if str(channel).lower() in {"telegram", "web", "email", "push", "webhook"}})
    if not channels:
        raise HTTPException(status_code=422, detail="At least one supported channel is required")
    alert_id = str(uuid4())
    async with get_session() as session:
        await session.execute(text(
            "INSERT INTO user_alerts(alert_id,user_id,instrument_id,asset,alert_type,condition,channels) "
            "VALUES(:id,:uid,:instrument,:asset,:type,CAST(:condition AS JSONB),CAST(:channels AS JSONB))"
        ), {"id": alert_id, "uid": int(user["id"]), "instrument": payload.instrument_id, "asset": (payload.asset or "").upper() or None, "type": payload.alert_type, "condition": json.dumps(payload.condition), "channels": json.dumps(channels)})
        await session.commit()
    return {"alert_id": alert_id, "active": True}


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    async with get_session() as session:
        result = await session.execute(text("UPDATE user_alerts SET active=FALSE,updated_at=NOW() WHERE alert_id=:id AND user_id=:uid"), {"id": alert_id, "uid": int(user["id"])})
        await session.commit()
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"disabled": True}


@router.post("/analytics/events", status_code=202)
async def analytics_event(request: Request, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    payload = await request.json()
    event_name = str(payload.get("event_name") or "").strip().lower()
    if not event_name or len(event_name) > 96:
        raise HTTPException(status_code=422, detail="Invalid event name")
    properties = dict(payload.get("properties") or {})
    # Prevent clients from sending secrets or arbitrary massive payloads.
    for forbidden in ("password", "token", "secret", "api_key", "private_key"):
        properties.pop(forbidden, None)
    encoded = json.dumps(properties, separators=(",", ":"), default=str)
    if len(encoded) > 12000:
        raise HTTPException(status_code=413, detail="Analytics payload too large")
    async with get_session() as session:
        await session.execute(text(
            "INSERT INTO analytics_events(event_id,user_id,event_name,source,session_id,properties) "
            "VALUES(gen_random_uuid()::text,:uid,:event_name,'app',:session_id,CAST(:properties AS JSONB))"
        ), {"uid": int(user["id"]), "event_name": event_name, "session_id": user.get("session_id"), "properties": encoded})
        await session.commit()
    return {"accepted": True}


__all__ = ["ACCESS_COOKIE", "REFRESH_COOKIE", "SESSION_COOKIE", "current_user", "router"]
