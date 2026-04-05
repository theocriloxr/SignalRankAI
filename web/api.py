from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.security import APIKeyHeader

from core.redis_state import state
from db.pg_features import list_signals_sent_today
from db.repository import (
    create_api_token,
    get_api_token_owner,
    get_latest_active_api_token_meta,
    revoke_api_token,
)
from db.session import get_session, is_db_configured

app = FastAPI()

API_KEY_HEADER = APIKeyHeader(name="X-API-Key")


def _now_utc() -> datetime:
    return datetime.utcnow()


def generate_api_key() -> str:
    return secrets.token_urlsafe(40)


async def get_user_by_apikey(
    request: Request,
    api_key: str = Depends(API_KEY_HEADER),
) -> int:
    if not is_db_configured():
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Dual-layer limit: per token + per IP.
    import hashlib
    token_key = f"api:token:{api_key[:8]}"
    ip_key = f"api:ip:{request.client.host if request.client else 'unknown'}"
    token_uid = int(hashlib.sha256(token_key.encode("utf-8")).hexdigest()[:12], 16)
    ip_uid = int(hashlib.sha256(ip_key.encode("utf-8")).hexdigest()[:12], 16)
    if await state.rate_limited(token_uid, limit=120, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many requests (token)")
    if await state.rate_limited(ip_uid, limit=240, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many requests (ip)")

    async with get_session() as session:
        owner = await get_api_token_owner(session, api_key, required_scope="signals:read")
        await session.commit()
        if owner is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return int(owner)


@app.get("/signals")
async def get_signals(
    user_id: int = Depends(get_user_by_apikey),
    limit: int = Query(10, ge=1, le=50),
):
    if not is_db_configured():
        raise HTTPException(status_code=503, detail="Database unavailable")
    async with get_session() as session:
        rows = await list_signals_sent_today(session, telegram_user_id=int(user_id))
        await session.commit()
        result = [
            {
                "signal_id": r.signal_id,
                "asset": r.asset,
                "timeframe": r.timeframe,
                "direction": r.direction,
                "entry": r.entry,
                "stop_loss": r.stop_loss,
                "take_profit": r.take_profit,
                "score": r.score,
            }
            for r in rows[:limit]
        ]
    return {"signals": result}


@app.post("/auth/tokens/rotate")
async def rotate_api_token(payload: dict):
    if not is_db_configured():
        raise HTTPException(status_code=503, detail="Database unavailable")
    telegram_user_id = int(payload.get("telegram_user_id") or 0)
    if not telegram_user_id:
        raise HTTPException(status_code=400, detail="telegram_user_id required")
    scope = str(payload.get("scope") or "signals:read")
    ttl_days = int(payload.get("ttl_days") or 30)
    ttl_days = max(1, min(ttl_days, 365))
    raw = generate_api_key()
    expires = _now_utc() + timedelta(days=ttl_days)

    async with get_session() as session:
        old_token = str(payload.get("old_token") or "").strip()
        if old_token:
            await revoke_api_token(session, old_token)
        await create_api_token(
            session,
            telegram_user_id=telegram_user_id,
            raw_token=raw,
            scope=scope,
            expires_at=expires,
        )
        await session.commit()
    return {"token": raw, "expires_at": expires.isoformat(), "scope": scope}


@app.post("/auth/tokens/revoke")
async def revoke_token(payload: dict):
    if not is_db_configured():
        raise HTTPException(status_code=503, detail="Database unavailable")
    raw = str(payload.get("token") or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="token required")
    async with get_session() as session:
        revoked = await revoke_api_token(session, raw)
        await session.commit()
    return {"revoked": revoked}


@app.get("/auth/tokens/current")
async def get_current_token_meta(
    telegram_user_id: int,
):
    if not is_db_configured():
        raise HTTPException(status_code=503, detail="Database unavailable")
    async with get_session() as session:
        meta = await get_latest_active_api_token_meta(session, int(telegram_user_id))
        await session.commit()
    if meta is None:
        raise HTTPException(status_code=404, detail="No active token")
    return meta
