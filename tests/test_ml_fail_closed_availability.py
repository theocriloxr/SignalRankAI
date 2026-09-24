import os
import unittest
from unittest.mock import patch

from ml.inference import MLFilter


class TestMLFailClosedAvailability(unittest.TestCase):
    @staticmethod
    def _inactive_filter():
        filt = MLFilter.__new__(MLFilter)
        filt.active = False
        filt.model = None
        filt.feature_cols = []
        return filt

    def test_unavailable_model_fails_closed_when_enabled(self):
        filt = self._inactive_filter()
        with patch.dict(os.environ, {"ML_FAIL_CLOSED_ON_UNAVAILABLE": "1"}, clear=False):
            approved, probability = filt.ml_filter({}, threshold=0.85)
        self.assertFalse(approved)
        self.assertIsNone(probability)

    def test_unavailable_model_keeps_compatibility_when_disabled(self):
        filt = self._inactive_filter()
        with patch.dict(os.environ, {"ML_FAIL_CLOSED_ON_UNAVAILABLE": "0"}, clear=False):
            approved, probability = filt.ml_filter({}, threshold=0.85)
        self.assertTrue(approved)
        self.assertIsNone(probability)


if __name__ == "__main__":
    unittest.main()
