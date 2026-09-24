import tempfile
from pathlib import Path
from unittest.mock import patch

from engine import ml as engine_ml


class _FakeBooster:
    def set_param(self, *_args, **_kwargs):
        return None


def test_unavailable_cached_model_retry_restores_durable_champion():
    original_cache = dict(engine_ml._MODEL_CACHE)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.json"
            path.write_text("{}", encoding="utf-8")
            engine_ml._MODEL_CACHE.update({
                "loaded": True,
                "booster": None,
                "feature_cols": [],
                "error": "feature_encoding_contract_mismatch",
            })
            with patch.object(engine_ml, "_model_path", return_value=path), patch.object(
                engine_ml, "_durable_model_retry_due", return_value=True
            ), patch.object(
                engine_ml, "_restore_durable_primary_if_enabled", return_value=True
            ) as restore, patch.object(
                engine_ml,
                "load_model_with_metadata",
                return_value=(_FakeBooster(), ["score_normalized"], {"version": "new"}, None),
            ):
                engine_ml._load_model()

            restore.assert_called_once_with(path)
            assert engine_ml._MODEL_CACHE["booster"] is not None
            assert engine_ml._MODEL_CACHE["version"] == "new"
    finally:
        engine_ml._MODEL_CACHE.clear()
        engine_ml._MODEL_CACHE.update(original_cache)
