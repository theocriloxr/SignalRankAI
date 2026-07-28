from __future__ import annotations

import json
from typing import Any, Mapping

from core.redis_state import state
from .types import AssetStrategyProfile, ProfileState


def _profile_from_mapping(payload: Mapping[str, Any], *, asset: str, asset_class: str) -> AssetStrategyProfile:
    raw_state=str(payload.get("state") or "RESEARCH").upper()
    try: profile_state=ProfileState(raw_state)
    except ValueError: profile_state=ProfileState.RESEARCH
    return AssetStrategyProfile(
        profile_id=str(payload.get("profile_id") or f"baseline:{asset}"), asset=str(payload.get("asset") or asset),
        asset_class=str(payload.get("asset_class") or asset_class), version=max(1,int(payload.get("version") or 1)),
        state=profile_state, source_scope=str(payload.get("source_scope") or "asset"),
        preferred_families=tuple(payload.get("preferred_families") or ()), penalised_families=tuple(payload.get("penalised_families") or ()), disabled_families=tuple(payload.get("disabled_families") or ()), preferred_timeframes=tuple(payload.get("preferred_timeframes") or ()), preferred_sessions=tuple(payload.get("preferred_sessions") or ()), avoided_sessions=tuple(payload.get("avoided_sessions") or ()), regime_weights=dict(payload.get("regime_weights") or {}), family_weights={str(k).lower():float(v) for k,v in dict(payload.get("family_weights") or {}).items()}, minimum_confidence=float(payload.get("minimum_confidence") or 0.70), minimum_reward_risk=float(payload.get("minimum_reward_risk") or 1.5), maximum_score_multiplier=min(1.25,max(1.0,float(payload.get("maximum_score_multiplier") or 1.15))), minimum_score_multiplier=max(0.70,min(1.0,float(payload.get("minimum_score_multiplier") or 0.85))), data_sufficiency_score=float(payload.get("data_sufficiency_score") or 0.0), sample_size=int(payload.get("sample_size") or 0), metadata=dict(payload.get("metadata") or {}),
    )


class ProfileResolver:
    """Resolve only approved/canary profiles from Redis; neutral fallback otherwise."""
    def resolve(self, asset: str, asset_class: str) -> AssetStrategyProfile:
        key=f"adaptive:profile:approved:{str(asset).upper()}"
        raw=state.get_sync(key)
        if raw:
            try:
                payload=json.loads(raw) if isinstance(raw,str) else dict(raw)
                profile=_profile_from_mapping(payload,asset=asset,asset_class=asset_class)
                if profile.approved_for_runtime:return profile
            except Exception: pass
        return AssetStrategyProfile(profile_id=f"baseline:{str(asset).upper()}",asset=str(asset).upper(),asset_class=asset_class,version=1,state=ProfileState.APPROVED,source_scope="global_baseline",family_weights={},minimum_confidence=0.70,maximum_score_multiplier=1.0,minimum_score_multiplier=1.0,data_sufficiency_score=0.0,sample_size=0,metadata={"neutral_fallback":True})
