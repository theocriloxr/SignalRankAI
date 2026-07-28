from __future__ import annotations

import logging, os
from typing import Any, Mapping

from data.fetcher import is_commodity, is_crypto, is_fx, is_index, is_stock
from market.session_classifier import get_current_session
from .components import DEFAULT_COMPONENTS
from .data_quality import assess_candle_quality, normalise_candles
from .profiles import ProfileResolver
from .sequence import sequence_reference
from .types import AdaptiveAssessment, Direction, MarketContext, StrategyEvidence, clamp

logger=logging.getLogger(__name__)

def _env_bool(name:str,default:bool=False)->bool:
    raw=os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1","true","yes","on","y"}

def _asset_class(asset:str)->str:
    if is_crypto(asset):return "crypto"
    if is_fx(asset):return "fx"
    if is_commodity(asset):return "commodity"
    if is_index(asset):return "index"
    if is_stock(asset):return "stock"
    return "unknown"

def _session(asset_class:str)->str:
    try:return str(get_current_session()[0] or "unknown").lower()
    except Exception:return "unknown"

def _bias(market_data:Mapping[str,Any])->str|None:
    for tf in ("1d","4h","1h"):
        d=market_data.get(tf)
        if not isinstance(d,Mapping):continue
        ind=d.get("indicators") or {};fast=ind.get("ema_fast",ind.get("ema_20"));slow=ind.get("ema_slow",ind.get("ema_50"))
        try:
            if float(fast)>float(slow)>0:return "LONG"
            if 0<float(fast)<float(slow):return "SHORT"
        except Exception:continue
    return None

class AdaptiveStrategyService:
    def __init__(self):
        self.profile_resolver=ProfileResolver();self.components=DEFAULT_COMPONENTS
    def evaluate(self, asset:str, market_data:Mapping[str,Any], regime:str|None)->AdaptiveAssessment:
        asset_class=_asset_class(asset);session=_session(asset_class);profile=self.profile_resolver.resolve(asset,asset_class);bias=_bias(market_data)
        evidence:list[StrategyEvidence]=[];refs=[];quality_scores=[]
        allowed_tfs=[x.strip() for x in (os.getenv("ADAPTIVE_EVALUATION_TIMEFRAMES") or "5m,15m,1h,4h,1d").split(",") if x.strip()]
        for tf in allowed_tfs:
            d=market_data.get(tf)
            if not isinstance(d,Mapping):continue
            candles=normalise_candles(d.get("candles") or [])
            quality=assess_candle_quality(candles,timeframe=tf,provider=str(d.get("source") or d.get("provider") or "unknown"),data_age_seconds=d.get("data_age_seconds"),minimum_candles=max(20,int(os.getenv("ADAPTIVE_MIN_CANDLES_PER_TIMEFRAME","30") or 30)))
            quality_scores.append(quality.score);refs.append(sequence_reference(asset,tf,d,pre_signal_candles=int(os.getenv("ADAPTIVE_PRE_SIGNAL_CANDLES","120") or 120)))
            context=MarketContext(asset=str(asset).upper(),asset_class=asset_class,timeframe=tf,candles=tuple(candles),indicators=dict(d.get("indicators") or {}),regime=str(regime or "unknown"),session=session,provider=quality.provider,data_quality=quality,higher_timeframe_bias=bias,news_context={"sentiment":market_data.get("news_sentiment")},macro_context=dict(market_data.get("_macro") or {}))
            for component in self.components:
                try:evidence.extend(component.evaluate(context))
                except Exception:logger.exception("[adaptive] component failed asset=%s tf=%s component=%s",asset,tf,getattr(component,"strategy_id",type(component).__name__))
        conflicts=[]
        active=[e for e in evidence if e.direction is not Direction.NEUTRAL and e.confidence>0]
        dirs={e.direction.value for e in active}
        if len(dirs)>1:conflicts.append("direction_conflict")
        mode="runtime_weighted" if profile.approved_for_runtime and not profile.metadata.get("neutral_fallback") else "shadow_observation"
        return AdaptiveAssessment(asset=str(asset).upper(),asset_class=asset_class,regime=str(regime or "unknown"),session=session,profile=profile,evidence=tuple(evidence),conflicts=tuple(conflicts),data_quality_score=(sum(quality_scores)/len(quality_scores) if quality_scores else 0.0),sequence_references=tuple(refs),runtime_mode=mode)
    def apply_to_signals(self, signals:list[dict[str,Any]], assessment:AdaptiveAssessment)->list[dict[str,Any]]:
        by_family:dict[str,list[StrategyEvidence]]={}
        for e in assessment.evidence:by_family.setdefault(e.family.lower(),[]).append(e)
        for signal in signals:
            family=str(signal.get("strategy_group") or signal.get("strategy_family") or "unknown").lower()
            multiplier=assessment.profile.family_multiplier(family,assessment.regime,assessment.session,str(signal.get("timeframe") or ""))
            signal["adaptive_profile_id"]=assessment.profile.profile_id;signal["adaptive_profile_version"]=assessment.profile.version;signal["adaptive_profile_state"]=assessment.profile.state.value;signal["adaptive_runtime_mode"]=assessment.runtime_mode;signal["adaptive_score_multiplier"]=multiplier
            signal["weight"]=float(signal.get("weight") or 1.0)*multiplier
            if signal.get("confidence") is not None:
                try:signal["confidence"]=clamp(float(signal["confidence"])*multiplier)
                except Exception:pass
            related=by_family.get(family,[])
            selected = related or [e for e in assessment.evidence if e.direction is not Direction.NEUTRAL]
            signal["adaptive_evidence"]=[e.to_dict() for e in sorted(selected,key=lambda x:x.confidence,reverse=True)[:8]]
            signal["adaptive_sequence_refs"]=list(assessment.sequence_references)
            signal["adaptive_conflicts"]=list(assessment.conflicts)
            signal["adaptive_data_quality_score"]=assessment.data_quality_score
        return signals
    def signal_candidates(self, assessment:AdaptiveAssessment)->list[dict[str,Any]]:
        if not _env_bool("ADAPTIVE_STRATEGY_GENERATION_ENABLED",True):return []
        if assessment.runtime_mode == "shadow_observation" and not _env_bool("ADAPTIVE_SHADOW_CANDIDATES_IN_SIGNAL_PIPELINE_ENABLED", False):
            return []
        threshold=max(0.55,float(os.getenv("ADAPTIVE_CANDIDATE_MIN_CONFIDENCE","0.72") or 0.72));out=[];seen=set()
        for e in sorted(assessment.evidence,key=lambda x:x.confidence,reverse=True):
            if e.direction is Direction.NEUTRAL or e.confidence<threshold or not e.entry_proposal or not e.stop_proposal or not e.target_proposals:continue
            if e.duplicate_fingerprint in seen:continue
            seen.add(e.duplicate_fingerprint);mult=assessment.profile.family_multiplier(e.family,assessment.regime,assessment.session,e.timeframe)
            if mult<=0:continue
            out.append({"asset":assessment.asset,"symbol":assessment.asset,"timeframe":e.timeframe,"direction":e.direction.value,"entry":e.entry_proposal,"stop":e.stop_proposal,"stop_loss":e.stop_proposal,"targets":list(e.target_proposals),"take_profit":list(e.target_proposals),"confidence":clamp(e.confidence*mult),"strength":clamp(e.confidence*mult),"strategy_name":e.strategy_id,"strategy_group":e.family,"reasoning":f"{e.setup_type}; structured adaptive evidence {e.strategy_version}","adaptive_profile_id":assessment.profile.profile_id,"adaptive_profile_version":assessment.profile.version,"adaptive_profile_state":assessment.profile.state.value,"adaptive_runtime_mode":assessment.runtime_mode,"adaptive_score_multiplier":mult,"adaptive_evidence":[e.to_dict()],"adaptive_sequence_refs":list(assessment.sequence_references),"adaptive_conflicts":list(assessment.conflicts),"adaptive_data_quality_score":assessment.data_quality_score,"adaptive_candidate":True,"source":"adaptive_strategy_intelligence"})
            if len(out)>=int(os.getenv("ADAPTIVE_MAX_CANDIDATES_PER_ASSET","3") or 3):break
        return out

_service:AdaptiveStrategyService|None=None
def get_adaptive_strategy_service()->AdaptiveStrategyService:
    global _service
    if _service is None:_service=AdaptiveStrategyService()
    return _service
