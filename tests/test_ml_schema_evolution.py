import base64
import json
import os
import tempfile
import unittest
from unittest.mock import patch


class TestMLSchemaVersioning(unittest.TestCase):
    def test_normalize_model_payload_adds_defaults(self):
        from ml.schema_version import normalize_model_payload

        payload = normalize_model_payload({"feature_cols": ["score"], "model_bytes_b64": "abc"})
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["model_format_version"], 1)
        self.assertEqual(payload["feature_cols"], ["score"])

    def test_legacy_model_b64_field_is_supported(self):
        from ml.schema_version import normalize_model_payload

        payload = normalize_model_payload({"feature_cols": ["score"], "model_b64": "abc"})
        self.assertEqual(payload["model_bytes_b64"], "abc")

    def test_migrate_feature_payload_fills_missing_with_zero(self):
        from ml.schema_version import migrate_feature_payload

        migrated = migrate_feature_payload({"score": "0.8"}, ["score", "rsi"])
        self.assertEqual(migrated["score"], 0.8)
        self.assertEqual(migrated["rsi"], 0.0)

    def test_inference_reads_schema_version_without_crashing(self):
        model_bytes = base64.b64encode(b"not_real_model").decode("utf-8")
        payload = {
            "feature_cols": ["score", "rsi"],
            "model_bytes_b64": model_bytes,
            "schema_version": 1,
            "model_format_version": 1,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(payload, tmp)
            tmp_path = tmp.name
        try:
            with patch.dict(os.environ, {"ML_ENABLED": "1", "ML_MODEL_PATH": tmp_path}, clear=False):
                from ml.inference import MLFilter

                ml_filter = MLFilter()
                self.assertFalse(ml_filter.active)  # invalid booster bytes -> fail-open
                self.assertIn(ml_filter.schema_version, (None, 1))
        finally:
            os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()

