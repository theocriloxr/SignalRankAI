from data.fetcher import validate_price_sanity


def test_legitimate_low_unit_price_crypto_is_not_treated_as_ghost_data():
    assert validate_price_sanity("BONKUSDT", 2.97e-6)
    assert validate_price_sanity("SHIBUSDT", 5.08e-6)
    assert validate_price_sanity("NFTUSDT", 2.429e-7)


def test_non_positive_crypto_price_remains_rejected():
    assert not validate_price_sanity("PEPEUSDT", 0.0)


def test_explicit_commodity_identity_bounds_remain_fail_closed():
    assert not validate_price_sanity("WTIUSD", 1.5)
