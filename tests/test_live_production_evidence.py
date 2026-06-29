from scripts.live_production_evidence import _asset_class, _wilson_interval


def test_wilson_interval_for_sparse_sample_is_wide() -> None:
    low, high = _wilson_interval(9, 24)
    assert 0.20 < low < 0.25
    assert 0.55 < high < 0.60


def test_wilson_interval_empty_sample_returns_zero_bounds() -> None:
    assert _wilson_interval(0, 0) == (0.0, 0.0)


def test_asset_class_aliases_supported_markets() -> None:
    assert _asset_class("BTCUSDT") == "crypto"
    assert _asset_class("EURUSD") == "forex"
    assert _asset_class("XAUUSD") == "commodity"
    assert _asset_class("AAPL") in {"equity", "stock"}
