from ml.features import extract_features


def test_macro_flow_into_extract_features():
    # Create a minimal signal and market_data with root _macro
    signal = {
        "asset": "BTCUSDT",
        "timeframe": "5m",
        "strategy": "EMA Trend",
    }

    market_data = {
        "5m": {
            "candles": [
                {"open": "99", "high": "101", "low": "98", "close": "100", "volume": "1"}
            ]
        },
        "_macro": {
            "dxy_trend": 0.73,
            "vix_trend": -0.21,
            "open_interest_change": 0.05,
            "funding_rate": 0.0005,
            "orderbook_imbalance": 0.12,
        },
    }

    features = extract_features(signal, market_data)

    assert float(features.get("dxy_trend", 0.0)) == 0.73
    assert float(features.get("vix_trend", 0.0)) == -0.21
    # funding_rate and open_interest_change are pulled from signal if present,
    # and macro provides other contextual series — ensure macro values don't break extraction
    assert "funding_rate" in features
    assert "open_interest_change" in features