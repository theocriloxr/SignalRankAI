from strategies.fibonacci_helpers import is_price_in_golden_pocket


def test_golden_pocket_inside_and_tolerance():
    swing_high = 200.0
    swing_low = 100.0
    # pocket boundaries
    pocket_low = swing_high - ((swing_high - swing_low) * 0.618)
    pocket_high = swing_high - ((swing_high - swing_low) * 0.786)

    mid = (pocket_low + pocket_high) / 2.0
    assert is_price_in_golden_pocket(mid, swing_high, swing_low)

    # test a price exactly at the lower boundary within tolerance
    assert is_price_in_golden_pocket(pocket_low, swing_high, swing_low, tol_pct=0.0001)
    # price slightly outside but within tolerance
    tiny = pocket_low - (abs(mid) * 0.00005)
    assert is_price_in_golden_pocket(tiny, swing_high, swing_low, tol_pct=0.0001)
