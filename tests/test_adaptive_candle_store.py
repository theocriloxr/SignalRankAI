from engine.adaptive.candle_store import enqueue_market_snapshot, queue_depth

def test_candle_capture_enqueues_only_changed_snapshot(monkeypatch):
    monkeypatch.setenv("ADAPTIVE_CANDLE_CAPTURE_ENABLED","1")
    rows=[{"open_time_ms":1700000000000+i*60000,"open":1,"high":2,"low":0.5,"close":1.5,"volume":10} for i in range(30)]
    market={"1m":{"candles":rows,"source":"test"}}
    before=queue_depth(); assert enqueue_market_snapshot("TEST",market)==1
    assert queue_depth()==before+1
    assert enqueue_market_snapshot("TEST",market)==0
