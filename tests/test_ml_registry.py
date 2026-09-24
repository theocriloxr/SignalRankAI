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

    def test_feature_schema_hash_is_order_sensitive_and_tamper_evident(self):
        from ml.model_registry import compute_feature_schema_hash, verify_feature_schema_integrity

        cols = ["score", "rr", "volatility"]
        payload = {
            "feature_cols": cols,
            "feature_schema_hash_sha256": compute_feature_schema_hash(cols),
        }
        ok, err = verify_feature_schema_integrity(payload)
        self.assertTrue(ok)
        self.assertIsNone(err)

        tampered = copy.deepcopy(payload)
        tampered["feature_cols"] = ["rr", "score", "volatility"]
        ok, err = verify_feature_schema_integrity(tampered)
        self.assertFalse(ok)
        self.assertEqual(err, "feature_schema_hash_mismatch")

    def test_save_model_payload_computes_hashes_and_lineage(self):
        import base64
        import hashlib
        import tempfile

        from ml.model_registry import compute_feature_schema_hash, save_model_payload

        class FakeBooster:
            def save_raw(self):
                return b"signalrank-model-bytes"

        features = ["score", "rr", "volatility"]
        metadata = {
            "version": "candidate-1",
            "artifact_hash_sha256": "0" * 64,
            "dataset_version": "dataset-20260924",
            "training_run_id": "run-abc",
            "parent_model_hash_sha256": "1" * 64,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.json"
            self.assertTrue(save_model_payload(path, FakeBooster(), features, metadata))
            payload = json.loads(path.read_text(encoding="utf-8"))

        raw = base64.b64decode(payload["model_bytes_b64"])
        self.assertEqual(payload["artifact_hash_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(
            payload["feature_schema_hash_sha256"],
            compute_feature_schema_hash(features),
        )
        self.assertEqual(payload["dataset_version"], "dataset-20260924")
        self.assertEqual(payload["training_run_id"], "run-abc")
        self.assertEqual(payload["parent_model_hash_sha256"], "1" * 64)

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
