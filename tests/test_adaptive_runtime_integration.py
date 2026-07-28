import os
from engine.adaptive.runtime import AdaptiveStrategyService

def _market():
    rows=[];p=100.0
    for i in range(90):
        o=p;c=p+(0.4 if i>60 else (0.1 if i%2 else -0.05));h=max(o,c)+0.25;l=min(o,c)-0.25
        rows.append({"open_time_ms":1_700_000_000_000+i*3_600_000,"open":o,"high":h,"low":l,"close":c,"volume":100+i})
        p=c
    return {"1h":{"candles":rows,"indicators":{"ema_fast":p,"ema_slow":p-2,"rsi":60,"adx":28,"macd":1},"source":"test","data_age_seconds":1}}

def test_runtime_attaches_profile_evidence_and_sequence_refs(monkeypatch):
    monkeypatch.setenv("ADAPTIVE_EVALUATION_TIMEFRAMES","1h")
    svc=AdaptiveStrategyService();assessment=svc.evaluate("BTCUSDT",_market(),"TRENDING")
    signal={"asset":"BTCUSDT","timeframe":"1h","strategy_group":"trend","confidence":0.8}
    out=svc.apply_to_signals([signal],assessment)[0]
    assert out["adaptive_profile_id"].startswith("baseline:")
    assert out["adaptive_sequence_refs"] and out["adaptive_data_quality_score"]>0
    assert out["adaptive_score_multiplier"]==1.0
