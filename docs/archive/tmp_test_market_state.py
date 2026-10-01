from unittest.mock import patch
fake_market = {
    "1h": {"candles":[{"time":1,"open":10,"high":11,"low":9,"close":10.5},{"time":2,"open":10.5,"high":12,"low":10,"close":11.0}],"indicators":{"rsi":55}},
    "1d": {"candles":[{"time":3,"open":9,"high":13,"low":8,"close":12.0}],"indicators":{"rsi":60}},
}
with patch('data.fetcher.fetch_market_data', return_value=fake_market):
    from engine.market_state import get_market_state
    ms = get_market_state('BTCUSDT',['1h','1d'], include_ml=False)
    print('MS:', ms)
