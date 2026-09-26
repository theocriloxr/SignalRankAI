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
            "schema_version": 3,
            "model_format_version": 3,
            "feature_encoding_version": "stable-sha256-v1",
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
        self.assertEqual(payload["schema_version"], 3)
        self.assertEqual(payload["model_format_version"], 3)
        self.assertEqual(payload["feature_encoding_version"], "stable-sha256-v1")

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



def test_training_dataset_version_is_deterministic_and_tamper_evident():
    import pandas as pd

    from ml.model_registry import compute_training_dataset_version

    features = pd.DataFrame(
        {
            "score": [0.5, 0.7, 0.9],
            "rr": [1.5, 2.0, 2.5],
        }
    )
    labels = pd.Series([0, 1, 1])
    timestamps = pd.to_datetime(
        ["2026-09-01T00:00:00Z", "2026-09-01T01:00:00Z", "2026-09-01T02:00:00Z"]
    )

    first = compute_training_dataset_version(features, labels, timestamps)
    second = compute_training_dataset_version(
        features.copy(), labels.copy(), timestamps.copy()
    )
    assert first == second
    assert first.startswith("sha256:")
    assert len(first) == 71

    changed_label = labels.copy()
    changed_label.iloc[0] = 1
    assert (
        compute_training_dataset_version(features, changed_label, timestamps)
        != first
    )

    reordered = features.iloc[::-1].reset_index(drop=True)
    assert (
        compute_training_dataset_version(
            reordered,
            labels.iloc[::-1].reset_index(drop=True),
            timestamps[::-1],
        )
        != first
    )


def _write_lineage_champion(path, raw: bytes = b"champion-model") -> str:
    import base64
    import hashlib

    payload = {
        "feature_cols": ["score", "rr"],
        "model_bytes_b64": base64.b64encode(raw).decode("ascii"),
        "artifact_hash_sha256": hashlib.sha256(raw).hexdigest(),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload["artifact_hash_sha256"]


def test_promotion_lineage_allows_first_champion_with_dataset_and_run(tmp_path):
    from ml.model_registry import evaluate_promotion_lineage

    decision = evaluate_promotion_lineage(
        dataset_version="sha256:" + "a" * 64,
        training_run_id="ml-run-1",
        parent_model_hash_sha256="",
        current_champion_path=tmp_path / "missing.json",
    )
    assert decision.eligible is True
    assert decision.reasons == ()


def test_promotion_lineage_requires_exact_current_champion_parent(tmp_path):
    from ml.model_registry import evaluate_promotion_lineage

    champion = tmp_path / "model.json"
    champion_hash = _write_lineage_champion(champion)

    good = evaluate_promotion_lineage(
        dataset_version="sha256:" + "b" * 64,
        training_run_id="ml-run-2",
        parent_model_hash_sha256=champion_hash,
        current_champion_path=champion,
    )
    assert good.eligible is True
    assert good.current_champion_hash_sha256 == champion_hash

    stale = evaluate_promotion_lineage(
        dataset_version="sha256:" + "b" * 64,
        training_run_id="ml-run-2",
        parent_model_hash_sha256="0" * 64,
        current_champion_path=champion,
    )
    assert stale.eligible is False
    assert "parent_model_hash_changed" in stale.reasons


def test_promotion_lineage_rejects_missing_run_or_dataset(tmp_path):
    from ml.model_registry import evaluate_promotion_lineage

    decision = evaluate_promotion_lineage(
        dataset_version="",
        training_run_id="",
        parent_model_hash_sha256="",
        current_champion_path=tmp_path / "missing.json",
    )
    assert decision.eligible is False
    assert "dataset_version_missing_or_invalid" in decision.reasons
    assert "training_run_id_missing" in decision.reasons


def test_serving_trainer_applies_lineage_gate_before_primary_selection():
    source = Path("ml/train_model.py").read_text(encoding="utf-8")
    fingerprint = source.index("compute_training_dataset_version")
    gate = source.index("evaluate_promotion_lineage")
    primary_selection = source.index(
        "target_path = primary_path if promotion_eligible else candidate_path"
    )
    assert fingerprint < gate < primary_selection
    assert '"dataset_version": dataset_version' in source
    assert '"parent_model_hash_sha256": parent_model_hash_sha256' in source


if __name__ == "__main__":
    unittest.main()
