import unittest

import pandas as pd

from ml.features import (
    FEATURE_ENCODING_VERSION,
    build_model_feature_values,
    direction_to_int,
    extract_features,
    regime_model_to_int,
    stable_category_to_int,
    strategy_model_to_int,
)
from ml.schema_version import FEATURE_COLUMNS_V3
from ml.train_model import engineer_features


class TestMLFeatureContract(unittest.TestCase):
    def test_stable_category_encoding_is_deterministic(self):
        self.assertEqual(FEATURE_ENCODING_VERSION, "stable-sha256-v1")
        self.assertEqual(direction_to_int("LONG"), direction_to_int("long"))
        self.assertEqual(regime_model_to_int("TRENDING"), regime_model_to_int("trending"))
        self.assertEqual(strategy_model_to_int("EMA Trend"), strategy_model_to_int("ema trend"))
        self.assertEqual(stable_category_to_int("BTCUSDT"), stable_category_to_int("BTCUSDT"))

    def test_extract_features_emits_complete_v3_contract(self):
        signal = {
            "asset": "BTCUSDT",
            "timeframe": "1h",
            "direction": "long",
            "strategy_name": "EMA Trend",
            "regime": "trending",
            "score": 82.0,
            "confidence": 0.76,
            "entry": 100.0,
            "stop_loss": 95.0,
            "take_profit": 112.0,
            "rr_ratio": 2.4,
        }
        market_data = {"1h": {"candles": [], "indicators": {}}, "_macro": {}}
        values = extract_features(signal, market_data)
        self.assertEqual(set(FEATURE_COLUMNS_V3) - set(values), set())
        canonical = build_model_feature_values(signal, market_data)
        for key in FEATURE_COLUMNS_V3:
            self.assertAlmostEqual(float(values[key]), float(canonical[key]))

    def test_training_uses_same_categorical_contract_as_inference(self):
        row = {
            "direction": "long",
            "regime": "trending",
            "strategy_name": "EMA Trend",
            "asset": "BTCUSDT",
            "timeframe": "1h",
            "rr_ratio": 2.0,
            "score": 80.0,
            "take_profit": 110.0,
            "entry": 100.0,
            "stop_loss": 95.0,
            "strength": 75.0,
            "asset_class_enc": 0.0,
            "price_velocity_3": 0.01,
            "price_velocity_5": 0.02,
            "price_velocity_10": 0.03,
            "price_acceleration_3_10": -0.02,
            "atr_rel": 0.01,
            "atr_regime": 1.0,
            "relative_volume": 1.2,
            "mtf_4h_trend": 1.0,
            "mtf_1d_trend": 1.0,
            "funding_rate": 0.0,
            "open_interest_change": 0.0,
            "dxy_trend": 0.0,
            "vix_trend": 0.0,
            "us10y_trend": 0.0,
            "yield_spread": 0.0,
            "minutes_since_high_impact_news": 999.0,
            "minutes_until_high_impact_news": 999.0,
            "news_event_impact_score": 0.0,
            "spx_trend": 0.0,
            "btc_corr": 0.0,
            "target": 1,
            "sample_weight": 1.0,
            "created_at": "2026-09-24T00:00:00",
        }
        matrix, _, cols, _, _ = engineer_features(pd.DataFrame([row]))
        values = dict(zip(cols, matrix.iloc[0].tolist()))
        self.assertEqual(int(values["direction_enc"]), direction_to_int("long"))
        self.assertEqual(int(values["regime_enc"]), regime_model_to_int("trending"))
        self.assertEqual(int(values["strategy_enc"]), strategy_model_to_int("EMA Trend"))


if __name__ == "__main__":
    unittest.main()
