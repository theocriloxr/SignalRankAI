from engine.adaptive.data_quality import assess_candle_quality
from engine.adaptive.components.order_flow import OrderFlowComponent
from engine.adaptive.components.price_action import PriceActionComponent
from engine.adaptive.profiles import _profile_from_mapping
from engine.adaptive.promotion import evaluate_profile_promotion
from engine.adaptive.types import MarketContext, ProfileState


def candles(n=80):
    out=[];p=100.0
    for i in range(n):
        o=p;c=p+(0.25 if i%3 else -0.08);h=max(o,c)+0.2;l=min(o,c)-0.2
        out.append({"open_time_ms":1_700_000_000_000+i*60_000,"open":o,"high":h,"low":l,"close":c,"volume":100+i})
        p=c
    return out

def context(rows):
    q=assess_candle_quality(rows,timeframe="1m",provider="test",data_age_seconds=1,minimum_candles=20)
    return MarketContext(asset="BTCUSDT",asset_class="crypto",timeframe="1m",candles=tuple(rows),indicators={"ema_fast":102,"ema_slow":100,"rsi":58,"adx":25,"macd":1},regime="TRENDING",session="london",provider="test",data_quality=q)

def test_quality_rejects_impossible_ohlc():
    rows=candles(30);rows[-1]["high"]=rows[-1]["low"]-1
    result=assess_candle_quality(rows,timeframe="1m",minimum_candles=20)
    assert not result.usable and result.impossible_count==1

def test_order_flow_never_fabricates_delta_from_volume():
    result=OrderFlowComponent().evaluate(context(candles()))
    assert result and result[0].setup_type=="order_flow_unavailable"
    assert result[0].evidence["candle_volume_not_used_as_order_flow"] is True

def test_confirmed_pattern_is_deterministic_for_same_cutoff():
    rows=candles();a=PriceActionComponent().evaluate(context(rows));b=PriceActionComponent().evaluate(context(list(rows)))
    assert [x.duplicate_fingerprint for x in a]==[x.duplicate_fingerprint for x in b]
    assert [x.evidence for x in a]==[x.evidence for x in b]

def test_profile_multiplier_is_bounded_and_requires_runtime_state():
    p=_profile_from_mapping({"profile_id":"x","state":"APPROVED","version":2,"family_weights":{"ict_smc":9}},asset="BTCUSDT",asset_class="crypto")
    assert p.state is ProfileState.APPROVED
    assert p.family_multiplier("ict_smc","trending","london","1h")<=1.25
    research=_profile_from_mapping({"profile_id":"r","state":"RESEARCH","family_weights":{"ict_smc":1.2}},asset="BTCUSDT",asset_class="crypto")
    assert research.family_multiplier("ict_smc","trending","london","1h")==1.0

def test_promotion_cannot_skip_human_approval_or_jump_to_approved():
    metrics={"sample_size":500,"positive_wfo_folds":5,"expectancy_r":0.2,"profit_factor":1.4,"max_drawdown_r":5,"brier_score":0.15}
    assert not evaluate_profile_promotion(metrics,human_approved=False,target_state="CANARY").eligible
    assert not evaluate_profile_promotion(metrics,human_approved=True,target_state="APPROVED").eligible
    assert evaluate_profile_promotion(metrics,human_approved=True,target_state="CANARY").eligible
