from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.security import APIKeyHeader
from db.session import get_session, ENGINE
from db.pg_features import get_or_create_user, list_signals_sent_today
import secrets
import os
import asyncio

app = FastAPI()

API_KEY_HEADER = APIKeyHeader(name="X-API-Key")

# In-memory API key store (for demo; replace with DB in production)
API_KEYS = {}

async def get_user_by_apikey(api_key: str = Depends(API_KEY_HEADER)):
    # In production, look up in DB
    for user_id, key in API_KEYS.items():
        if key == api_key:
            return user_id
    raise HTTPException(status_code=401, detail="Invalid API key")

@app.get("/signals")
async def get_signals(user_id: int = Depends(get_user_by_apikey), limit: int = Query(10, le=50)):
    if ENGINE is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    async with get_session() as session:
        rows = await list_signals_sent_today(session, telegram_user_id=int(user_id))
        # Return up to 'limit' signals
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

def generate_api_key():
    return secrets.token_urlsafe(32)

# Utility for Telegram bot to set/get API keys
# In production, store in DB

def set_user_api_key(user_id, key):
    API_KEYS[user_id] = key

def get_user_api_key(user_id):
    return API_KEYS.get(user_id)
