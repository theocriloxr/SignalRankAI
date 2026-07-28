from __future__ import annotations

import json, logging, os
from datetime import datetime
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from core.redis_state import state
from db.session import get_session

logger=logging.getLogger(__name__)

async def persist_signal_adaptive_evidence(session:AsyncSession, signal:Any, payload:Mapping[str,Any])->None:
    evidence=list(payload.get("adaptive_evidence") or [])[:16];refs=list(payload.get("adaptive_sequence_refs") or [])[:8]
    for item in evidence:
        await session.execute(text("""INSERT INTO adaptive_signal_evidence(signal_id,asset,timeframe,strategy_id,strategy_version,family,direction,setup_type,confidence,raw_score,evidence_quality,profile_id,profile_version,regime,data_quality,evidence,conflicts,duplicate_fingerprint,created_at) VALUES(:signal_id,:asset,:timeframe,:strategy_id,:strategy_version,:family,:direction,:setup_type,:confidence,:raw_score,:evidence_quality,:profile_id,:profile_version,:regime,CAST(:data_quality AS JSONB),CAST(:evidence AS JSONB),CAST(:conflicts AS JSONB),:duplicate_fingerprint,NOW()) ON CONFLICT(signal_id,duplicate_fingerprint) DO NOTHING"""),{"signal_id":signal.signal_id,"asset":signal.asset,"timeframe":str(item.get("timeframe") or signal.timeframe),"strategy_id":str(item.get("strategy_id") or "unknown")[:128],"strategy_version":str(item.get("strategy_version") or "unknown")[:64],"family":str(item.get("family") or "unknown")[:64],"direction":str(item.get("direction") or signal.direction)[:16],"setup_type":str(item.get("setup_type") or "unknown")[:128],"confidence":float(item.get("confidence") or 0.0),"raw_score":float(item.get("raw_score") or 0.0),"evidence_quality":str(item.get("evidence_quality") or "genuine")[:24],"profile_id":str(payload.get("adaptive_profile_id") or "")[:128] or None,"profile_version":int(payload.get("adaptive_profile_version") or 0) or None,"regime":str(payload.get("regime") or signal.regime or "unknown")[:32],"data_quality":json.dumps(item.get("data_quality") or {}),"evidence":json.dumps(item.get("evidence") or {}),"conflicts":json.dumps(item.get("conflicts") or []),"duplicate_fingerprint":str(item.get("duplicate_fingerprint") or "")[:64]})
    for ref in refs:
        await session.execute(text("""INSERT INTO adaptive_signal_sequences(signal_id,asset,timeframe,sequence_hash,candle_count,start_time_ms,end_time_ms,provider,evidence_stage,summary,created_at) VALUES(:signal_id,:asset,:timeframe,:sequence_hash,:candle_count,:start_time_ms,:end_time_ms,:provider,:evidence_stage,CAST(:summary AS JSONB),NOW()) ON CONFLICT(signal_id,timeframe,evidence_stage,sequence_hash) DO NOTHING"""),{"signal_id":signal.signal_id,"asset":signal.asset,"timeframe":str(ref.get("timeframe") or signal.timeframe),"sequence_hash":str(ref.get("sequence_hash") or "")[:64],"candle_count":int(ref.get("candle_count") or 0),"start_time_ms":ref.get("start_time_ms"),"end_time_ms":ref.get("end_time_ms"),"provider":str(ref.get("provider") or "unknown")[:64],"evidence_stage":str(ref.get("evidence_stage") or "pre_signal")[:24],"summary":json.dumps(ref.get("summary") or {})})

async def publish_approved_profiles()->int:
    async with get_session(priority="background",label="adaptive.publish_profiles",timeout_seconds=float(os.getenv("ADAPTIVE_DB_TIMEOUT_SECONDS","4") or 4)) as session:
        rows=(await session.execute(text("""SELECT profile_id,asset,asset_class,version,state,source_scope,preferred_families,penalised_families,disabled_families,preferred_timeframes,preferred_sessions,avoided_sessions,regime_weights,family_weights,minimum_confidence,minimum_reward_risk,maximum_score_multiplier,minimum_score_multiplier,data_sufficiency_score,sample_size,metadata FROM adaptive_asset_profiles WHERE state IN ('APPROVED','LIMITED_LIVE','CANARY') AND is_current=TRUE"""))).mappings().all()
    for row in rows:
        payload=dict(row)
        for key in ("preferred_families","penalised_families","disabled_families","preferred_timeframes","preferred_sessions","avoided_sessions"):
            payload[key]=payload.get(key) or []
        state.set_sync(f"adaptive:profile:approved:{str(payload['asset']).upper()}",json.dumps(payload,default=str),ex=21600)
    return len(rows)


def invalidate_profile_cache(asset: str, *, state_name: str = "SUSPENDED") -> None:
    """Immediately prevent a stale approved profile from remaining active in Redis."""
    state.set_sync(
        f"adaptive:profile:approved:{str(asset).upper()}",
        json.dumps({"asset": str(asset).upper(), "state": str(state_name).upper()}),
        ex=21600,
    )
