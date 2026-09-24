import os
import unittest
from unittest.mock import patch

from engine.ml import _feature_vector


class TestMLStrictSchema(unittest.TestCase):
    def test_strict_schema_rejects_missing_model_feature(self):
        signal = {
            "asset": "BTCUSDT",
            "score": 80,
            "rr_ratio": 2.0,
            "entry": 100.0,
            "stop_loss": 95.0,
            "take_profit": 110.0,
        }
        with patch.dict(os.environ, {"ML_STRICT_SCHEMA": "1"}, clear=False):
            vector = _feature_vector(signal, ["score_normalized", "feature_not_available"])
        self.assertIsNone(vector)

    def test_permissive_schema_keeps_backward_compatible_zero_fill(self):
        signal = {
            "asset": "BTCUSDT",
            "score": 80,
            "rr_ratio": 2.0,
            "entry": 100.0,
            "stop_loss": 95.0,
            "take_profit": 110.0,
        }
        with patch.dict(os.environ, {"ML_STRICT_SCHEMA": "0"}, clear=False):
            vector = _feature_vector(signal, ["score_normalized", "feature_not_available"])
        self.assertIsNotNone(vector)
        self.assertEqual(tuple(vector.shape), (1, 2))
        self.assertAlmostEqual(float(vector[0, 0]), 0.8)
        self.assertAlmostEqual(float(vector[0, 1]), 0.0)


if __name__ == "__main__":
    unittest.main()
