"""Owner-supplied top-down order-block strategy (videos of 23 Jun and 6 Aug 2026).

The synthetic chart reproduces what the recordings show and narrate: an
uptrend with a prior swing low, a base candle, a strong bearish displacement
(supply order block), a 4h break of structure below that swing low, a return to
the block in the premium half of the range, and a 15m ABC (A high, B low, C
higher high taking A) followed by the first close below B.
"""
from __future__ import annotations

from strategies import zone_rejection as zr

ON = {"ZONE_REJECTION_STRATEGY_ENABLED": "1"}


def _bar(o, h, l, c, ts):
    return {"open": o, "high": h, "low": l, "close": c, "timestamp": ts, "volume": 100}


def _htf():
    bars, price = [], 100.0
    for i in range(30):  # gentle uptrend with one dip that becomes the prior swing low
        step = -1.6 if i == 24 else (0.9 if i == 25 else 0.55)
        o = price + (0.2 if i == 25 else 0.0)
        c = o + step
        bars.append(_bar(o, max(o, c) + 0.3, min(o, c) - 0.3, c, i))
        price = c
    base_open = price
    bars.append(_bar(base_open, base_open + 1.4, base_open - 0.2, base_open + 1.0, 30))       # base (up-close)
    for j, close in enumerate((base_open - 2.5, base_open - 5.5, base_open - 8.5)):            # displacement
        o = bars[-1]["close"]
        bars.append(_bar(o, o + 0.2, close - 0.3, close, 31 + j))
    for j, close in enumerate((base_open - 10, base_open - 11, base_open - 9, base_open - 7,   # BOS, then retrace
                               base_open - 5, base_open - 3, base_open - 1.6)):
        o = bars[-1]["close"]
        bars.append(_bar(o, max(o, close) + 0.3, min(o, close) - 0.3, close, 34 + j))
    zone_low, zone_high = base_open - 0.2, base_open + 1.4
    o = bars[-1]["close"]
    bars.append(_bar(o, zone_low + 0.4, o - 0.2, zone_low + 0.1, 41))                         # last bar enters zone
    return bars, zone_low, zone_high


def _exec(zone_low, c_high=0.80, break_b=True, already_broken=False):
    z = zone_low
    bars, price = [], z - 2.0
    for i in range(44):  # steady approach from below, no swings
        o, c = price, price + 0.04
        bars.append(_bar(o, c + 0.02, o - 0.02, c, i))
        price = c
    shape = [  # (high, low, close) relative to the zone low
        (0.30, 0.15, 0.25), (0.40, 0.25, 0.35), (0.50, 0.35, 0.40),   # A at 0.50
        (0.42, 0.20, 0.25), (0.30, 0.12, 0.18), (0.25, 0.05, 0.20),   # B at 0.05
        (0.45, 0.15, 0.40), (0.60, 0.30, 0.55), (c_high, 0.50, 0.55), # C
        (0.60, 0.35, 0.40), (0.45, 0.20, 0.22),
    ]
    if already_broken:
        shape[-1] = (0.45, -0.05, 0.00)  # B was already closed through before the last bar
    for j, (h, l, c) in enumerate(shape):
        o = bars[-1]["close"]
        bars.append(_bar(o, z + max(h, o - z, c), z + min(l, o - z, c), z + c, 44 + j))
    o = bars[-1]["close"]
    close = z - 0.02 if break_b else z + 0.12
    bars.append(_bar(o, max(o, close) + 0.03, min(o, close) - 0.03, close, 44 + len(shape)))
    return bars


def _market(daily=None, **exec_kwargs):
    htf, zone_low, zone_high = _htf()
    market = {"4h": {"candles": htf}, "15m": {"candles": _exec(zone_low, **exec_kwargs)}}
    if daily is not None:
        market["1d"] = {"candles": daily}
    return market, zone_low, zone_high


def _shorts(market, **kwargs):
    return [s for s in zr.zone_rejection_strategies("XAUUSD", market, environment=ON, **kwargs)
            if s["direction"] == "SHORT"]


def test_disabled_by_default_and_without_flag():
    market, _, _ = _market()
    assert zr.zone_rejection_strategies("XAUUSD", market, environment={}) == []
    assert zr.zone_rejection_strategies("XAUUSD", market, environment={"ZONE_REJECTION_STRATEGY_ENABLED": "0"}) == []


def test_fresh_supply_zone_is_found_and_touched_zones_are_not():
    htf, zone_low, zone_high = _htf()
    rows = zr._ohlc(htf)
    supply = [z for z in zr.find_fresh_zones(rows, "4h", zr.ZoneConfig()) if z.kind == "supply"]
    assert any(abs(z.low - zone_low) < 1e-9 and abs(z.high - zone_high) < 1e-9 for z in supply)
    touched = list(rows)
    touched[-2] = (rows[-2][0], zone_low + 0.1, rows[-2][2], rows[-2][3])  # an earlier bar re-entered the zone
    assert not any(abs(z.low - zone_low) < 1e-9 for z in zr.find_fresh_zones(touched, "4h", zr.ZoneConfig())
                   if z.kind == "supply")


def test_abc_break_in_the_premium_order_block_produces_a_short():
    market, zone_low, zone_high = _market()
    shorts = _shorts(market)
    assert shorts
    sig = shorts[0]
    assert sig["stop_loss"] > sig["entry"] > sig["take_profit"]
    assert sig["take_profit"] >= sig["equilibrium"]          # never beyond the 50% target
    assert sig["entry"] > sig["equilibrium"]                  # premium half only
    assert sig["rr_ratio"] >= zr.ZoneConfig().min_rr
    assert abs(sig["swept_level"] - (zone_low + 0.50)) < 1e-9  # C took A's liquidity
    assert sig["strategy_name"] == zr.STRATEGY_NAME and sig["strategy_version"] == zr.STRATEGY_VERSION
    assert sig["timeframe"] == "15m" and sig["strategy_group"] == "zones"


def test_no_entry_without_c_taking_a_or_without_the_b_break():
    assert _shorts(_market(c_high=0.45)[0]) == []          # C below A: no liquidity taken
    assert _shorts(_market(break_b=False)[0]) == []         # B never broken
    assert _shorts(_market(already_broken=True)[0]) == []   # only the first close through B counts


def test_sells_are_refused_in_the_discount_half_of_the_daily_range():
    htf, zone_low, _ = _htf()
    daily = [_bar(150.0, 160.0, 149.0, 155.0, i) for i in range(30)] + htf[-30:]
    assert _shorts(_market(daily=daily)[0]) == []


def test_minimum_reward_to_risk_is_enforced():
    market, _, _ = _market()
    assert _shorts(market, config=zr.ZoneConfig(min_rr=1000.0)) == []


def test_no_look_ahead_the_decision_needs_the_closed_break_bar():
    market, _, _ = _market()
    assert _shorts(market)
    truncated = {tf: {"candles": data["candles"][:-1]} for tf, data in market.items()}
    assert _shorts(truncated) == []


def test_daily_zone_maps_to_4h_by_time_and_is_skipped_without_timestamps():
    assert zr.map_index([10, 20, 30], 1, [5, 15, 25, 35]) == 2
    assert zr.map_index([None, None], 1, [1, 2]) is None
    market, _, _ = _market()
    no_stamps = {tf: {"candles": [{k: v for k, v in c.items() if k != "timestamp"} for c in d["candles"]]}
                 for tf, d in market.items()}
    daily = {"1d": no_stamps["4h"], **no_stamps}
    assert zr.zone_rejection_strategies("XAUUSD", daily, environment=ON) == []


def test_invalid_candles_are_rejected_not_guessed():
    market, _, _ = _market()
    market["15m"]["candles"][-1]["high"] = market["15m"]["candles"][-1]["low"] - 1  # impossible bar
    assert zr.zone_rejection_strategies("XAUUSD", market, environment=ON) == []


def test_daily_order_block_with_timestamps_reaches_the_same_entry():
    htf, _, _ = _htf()
    market, _, _ = _market(daily=[dict(bar) for bar in htf])
    shorts = _shorts(market)
    assert shorts and shorts[0]["zone_timeframe"] == "1d"


def test_engine_dispatches_the_zones_group_once_per_asset_on_its_execution_timeframe(monkeypatch):
    import strategies
    from strategies.capabilities import strategy_is_supported

    calls = []
    monkeypatch.setattr(strategies, "_certified_strategy_market_data", lambda asset, cls, data: data)
    monkeypatch.setattr(strategies, "zone_rejection_strategies",
                        lambda asset, data: calls.append(asset) or [])
    monkeypatch.setenv("ADAPTIVE_CANDLE_CAPTURE_ENABLED", "0")
    monkeypatch.setenv("ADAPTIVE_STRATEGY_ENGINE_ENABLED", "0")
    monkeypatch.setenv("IMP_STRATEGY_ENABLED", "0")
    candles = [{"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "timestamp": i} for i in range(5)]
    market = {tf: {"candles": candles, "indicators": {}} for tf in ("5m", "15m", "1h", "4h")}
    strategies.run_all_strategies("EURUSD", market, "TRENDING")
    assert calls == ["EURUSD"]
    assert strategy_is_supported("zones", "forex", "15m", "TRENDING")
    assert not strategy_is_supported("zones", "forex", "1d", "TRENDING")
