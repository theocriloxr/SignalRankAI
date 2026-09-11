from datetime import datetime, timezone

from market.data_quality_certification import certify_market_candles


def _rows(count=30, *, seconds=3600, start=None):
    start = start or int(datetime(2026, 8, 24, tzinfo=timezone.utc).timestamp())
    return [
        {"timestamp": (start + i * seconds) * 1000, "open": 100, "high": 102, "low": 99, "close": 101, "volume": 10}
        for i in range(count)
    ]


def test_crypto_gap_quarantines_instrument():
    rows = _rows()
    rows[20]["timestamp"] += 7200 * 1000
    result = certify_market_candles(rows, asset_class="crypto", timeframe="1h")
    assert result.quarantined
    assert any(reason.startswith("unexpected_session_gaps") for reason in result.reasons)


def test_stock_overnight_closure_is_not_an_intraday_gap():
    friday = int(datetime(2026, 8, 28, 14, tzinfo=timezone.utc).timestamp())
    first = _rows(8, start=friday)
    monday = int(datetime(2026, 8, 31, 14, tzinfo=timezone.utc).timestamp())
    rows = first + _rows(22, start=monday)
    result = certify_market_candles(rows, asset_class="stock", timeframe="1h")
    assert result.session_gap_count == 0


def test_fx_friday_to_sunday_open_is_not_a_provider_gap():
    friday = int(datetime(2026, 8, 28, 21, tzinfo=timezone.utc).timestamp())
    sunday = int(datetime(2026, 8, 30, 22, tzinfo=timezone.utc).timestamp())
    rows = _rows(15, seconds=3600, start=friday - (14 * 3600))
    rows += _rows(15, seconds=3600, start=sunday)
    result = certify_market_candles(rows, asset_class="fx", timeframe="1h")
    assert result.session_gap_count == 0


def test_fx_midweek_gap_is_quarantined():
    rows = _rows()
    rows[20]["timestamp"] += 4 * 3600 * 1000
    result = certify_market_candles(rows, asset_class="fx", timeframe="1h")
    assert result.quarantined
    assert any(reason.startswith("unexpected_session_gaps") for reason in result.reasons)


def test_impossible_ohlc_and_duplicate_timestamp_quarantine():
    rows = _rows()
    rows[4]["high"] = 90
    rows[5]["timestamp"] = rows[4]["timestamp"]
    result = certify_market_candles(rows, asset_class="fx", timeframe="1h")
    assert result.quarantined
    assert any(reason.startswith("impossible_ohlc") for reason in result.reasons)
    assert any(reason.startswith("duplicates") for reason in result.reasons)


def test_futures_require_expiry_and_roll_metadata():
    result = certify_market_candles(
        _rows(), asset_class="commodity", timeframe="1h",
        metadata={"instrument_type": "future"},
    )
    assert result.quarantined
    assert "missing_contract_roll_metadata" in result.reasons


def test_index_feed_type_must_be_explicit_when_certified():
    result = certify_market_candles(_rows(), asset_class="index", timeframe="1h")
    assert result.quarantined
    assert "ambiguous_index_feed_type" in result.reasons


def test_yfinance_index_feed_is_inferred_as_cash_index():
    result = certify_market_candles(
        _rows(),
        asset_class="index",
        timeframe="1h",
        provider="yfinance",
    )
    assert result.usable
    assert result.feed_type == "cash_index"
