import copy
import json
import unittest
from pathlib import Path


class TestModelRegistry(unittest.TestCase):
    def _load_payload(self):
        p = Path("ml/model.json")
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_integrity_passes_for_repo_model(self):
        from ml.model_registry import verify_artifact_integrity

        payload = self._load_payload()
        ok, err = verify_artifact_integrity(payload)
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_integrity_detects_hash_mismatch(self):
        from ml.model_registry import verify_artifact_integrity

        payload = self._load_payload()
        bad = copy.deepcopy(payload)
        bad["artifact_hash_sha256"] = "0" * 64
        ok, err = verify_artifact_integrity(bad)
        self.assertFalse(ok)
        self.assertEqual(err, "artifact_hash_mismatch")

    def test_load_model_with_metadata(self):
        try:
            import xgboost as xgb  # noqa: F401
        except Exception:
            self.skipTest("xgboost not available")

        from ml.model_registry import load_model_with_metadata
        import xgboost as xgb

        path = Path("ml/model.json")
        booster, feature_cols, metadata, err = load_model_with_metadata(path, xgb)
        self.assertIsNone(err)
        self.assertIsNotNone(booster)
        self.assertGreater(len(feature_cols), 0)
        self.assertIn("version", metadata)


if __name__ == "__main__":
    unittest.main()
