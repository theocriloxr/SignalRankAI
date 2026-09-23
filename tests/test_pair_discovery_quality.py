from data.pair_discovery import _filter_blacklisted


def test_quote_inventory_cannot_become_synthetic_usdt_markets():
    candidates = ["BTCUSDT", "UBUSDT", "USDGUSDT", "USATUSDT", "USDCVUSDT"]
    assert _filter_blacklisted(candidates) == ["BTCUSDT"]
