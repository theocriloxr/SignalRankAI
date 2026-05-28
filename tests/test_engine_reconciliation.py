from engine.core import _counts_from_active_trades


def test_counts_from_active_trades_uses_live_redis_payloads():
    active_trades = {
        "sig_1": {"signal": {"asset": "BTCUSDT"}},
        "sig_2": {"signal": {"asset": "BTCUSDT"}},
        "sig_3": {"signal": {"asset": "EURUSD"}},
        "sig_4": {"asset": "XAUUSD"},
    }

    asset_counts, class_counts = _counts_from_active_trades(active_trades)

    assert asset_counts["BTCUSDT"] == 2
    assert asset_counts["EURUSD"] == 1
    assert asset_counts["XAUUSD"] == 1
    assert class_counts["crypto"] == 2
    assert class_counts["fx"] == 1
    assert class_counts["commodity"] == 1


def test_counts_from_active_trades_ignores_bad_payloads():
    active_trades = {
        "sig_1": None,
        "sig_2": {"signal": "not-a-dict"},
        "sig_3": {"signal": {}},
    }

    asset_counts, class_counts = _counts_from_active_trades(active_trades)

    assert asset_counts == {}
    assert class_counts == {}