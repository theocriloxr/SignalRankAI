"""Authenticated `/api/v1` router.

Raw API keys are returned only at creation. Stored tokens are hashed by the
repository and every mutation derives identity from the authenticated token.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from core.redis_state import state
from db.pg_features import list_signals_sent_today
from db.repository import (
    create_api_token,
    get_api_token_owner,
    get_latest_active_api_token_meta,
    revoke_api_token,
)
from db.session import get_session, is_db_configured

router = APIRouter()
logger = logging.getLogger(__name__)

_API_KEY = APIKeyHeader(name="X-API-Key", auto_error=False)
_BEARER = HTTPBearer(auto_error=False)


class RotateTokenRequest(BaseModel):
    scope: str = Field(default="signals:read", pattern=r"^(signals:read|signals:\*)$")
    ttl_days: int = Field(default=30, ge=1, le=365)


class RevokeTokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=256)


def generate_api_key() -> str:
    return "srk_" + secrets.token_urlsafe(40)


def _extract_token(
    api_key: str | None,
    bearer: HTTPAuthorizationCredentials | None,
) -> str:
    token = str(api_key or (bearer.credentials if bearer else "") or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="API key required")
    return token


async def authenticate_api_key(
    request: Request,
    required_scope: str = "signals:read",
    api_key: str | None = Depends(_API_KEY),
    bearer: HTTPAuthorizationCredentials | None = Depends(_BEARER),
) -> int:
    if not is_db_configured():
        raise HTTPException(status_code=503, detail="Database unavailable")
    token = _extract_token(api_key, bearer)

    token_uid = int(hashlib.sha256(f"token:{token}".encode()).hexdigest()[:16], 16)
    client_host = request.client.host if request.client else "unknown"
    ip_uid = int(hashlib.sha256(f"ip:{client_host}".encode()).hexdigest()[:16], 16)
    if await state.rate_limited(token_uid, limit=120, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many requests (token)")
    if await state.rate_limited(ip_uid, limit=240, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many requests (ip)")

    async with get_session() as session:
        owner = await get_api_token_owner(session, token, required_scope=required_scope)
        await session.commit()
    if owner is None:
        raise HTTPException(status_code=401, detail="Invalid, expired, revoked, or insufficient API key")
    return int(owner)


async def get_user_by_apikey(
    request: Request,
    api_key: str | None = Depends(_API_KEY),
    bearer: HTTPAuthorizationCredentials | None = Depends(_BEARER),
) -> int:
    return await authenticate_api_key(request, "signals:read", api_key, bearer)


@router.get("/signals")
async def get_signals(
    user_id: int = Depends(get_user_by_apikey),
    limit: int = Query(10, ge=1, le=50),
):
    async with get_session() as session:
        rows = await list_signals_sent_today(session, telegram_user_id=int(user_id))
        await session.commit()
    return {
        "signals": [
            {
                "signal_id": row.signal_id,
                "asset": row.asset,
                "timeframe": row.timeframe,
                "direction": row.direction,
                "entry": row.entry,
                "stop_loss": row.stop_loss,
                "take_profit": row.take_profit,
                "score": row.score,
            }
            for row in rows[:limit]
        ]
    }


@router.post("/auth/tokens/rotate")
async def rotate_api_token(
    payload: RotateTokenRequest,
    owner_id: int = Depends(get_user_by_apikey),
):
    raw = generate_api_key()
    expires = datetime.utcnow() + timedelta(days=payload.ttl_days)
    try:
        async with get_session() as session:
            # Revoke all access represented by the current credential only when
            # the caller explicitly revokes it; rotation creates a parallel key
            # so clients can switch without an outage.
            await create_api_token(
                session,
                telegram_user_id=int(owner_id),
                raw_token=raw,
                scope=payload.scope,
                expires_at=expires,
            )
            await session.commit()
    except Exception as exc:
        logger.warning("[api] token rotation unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Token service unavailable") from exc
    return {"token": raw, "expires_at": expires.isoformat(), "scope": payload.scope}


@router.post("/auth/tokens/revoke")
async def revoke_token(
    payload: RevokeTokenRequest,
    owner_id: int = Depends(get_user_by_apikey),
):
    async with get_session() as session:
        target_owner = await get_api_token_owner(session, payload.token, required_scope="")
        if target_owner is None:
            raise HTTPException(status_code=404, detail="Token not found")
        if int(target_owner) != int(owner_id):
            raise HTTPException(status_code=403, detail="Cannot revoke another user's token")
        revoked = await revoke_api_token(session, payload.token)
        await session.commit()
    return {"revoked": revoked}


@router.get("/auth/tokens/current")
async def get_current_token_meta(owner_id: int = Depends(get_user_by_apikey)):
    async with get_session() as session:
        meta = await get_latest_active_api_token_meta(session, int(owner_id))
        await session.commit()
    if meta is None:
        raise HTTPException(status_code=404, detail="No active token")
    return meta


# Compatibility application for imports that previously served web.api alone.
app = FastAPI(title="SignalRankAI API")
app.include_router(router, prefix="/api/v1")


__all__ = [
    "app",
    "authenticate_api_key",
    "generate_api_key",
    "get_user_by_apikey",
    "router",
]
