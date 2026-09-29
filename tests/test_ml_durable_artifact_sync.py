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


def test_training_candidate_reload_can_skip_durable_restore(monkeypatch, tmp_path):
    path = tmp_path / "model_candidate.json"
    path.write_text('{"fresh": true}', encoding="utf-8")
    original = dict(engine_ml._SHADOW_CACHE)
    try:
        monkeypatch.setenv("ML_CANDIDATE_MODEL_PATH", str(path))
        with patch.object(
            engine_ml,
            "_restore_durable_candidate_if_enabled",
            side_effect=AssertionError("fresh candidate must not be overwritten"),
        ) as restore, patch.object(
            engine_ml,
            "load_model_with_metadata",
            return_value=(
                _FakeBooster(),
                ["score_normalized"],
                {"version": "fresh-candidate", "metrics": {"classification_threshold": 0.5}},
                None,
            ),
        ):
            status = engine_ml.reload_shadow_model(sync_durable=False)

        restore.assert_not_called()
        assert status["loaded"] is True
        assert status["version"] == "fresh-candidate"
    finally:
        engine_ml._SHADOW_CACHE.clear()
        engine_ml._SHADOW_CACHE.update(original)


def test_training_primary_reload_can_skip_durable_restore(monkeypatch, tmp_path):
    path = tmp_path / "model.json"
    path.write_text('{"fresh": true}', encoding="utf-8")
    original = dict(engine_ml._MODEL_CACHE)
    try:
        with patch.object(engine_ml, "_model_path", return_value=path), patch.object(
            engine_ml,
            "_restore_durable_primary_if_enabled",
            side_effect=AssertionError("fresh champion must not be overwritten"),
        ) as restore, patch.object(
            engine_ml,
            "load_model_with_metadata",
            return_value=(
                _FakeBooster(),
                ["score_normalized"],
                {"version": "fresh-primary", "trained_at": "now"},
                None,
            ),
        ):
            status = engine_ml.reload_model(sync_durable=False)

        restore.assert_not_called()
        assert status["loaded"] is True
        assert status["version"] == "fresh-primary"
    finally:
        engine_ml._MODEL_CACHE.clear()
        engine_ml._MODEL_CACHE.update(original)


def test_loaded_shadow_model_hot_reloads_when_durable_file_changes(monkeypatch, tmp_path):
    path = tmp_path / "model_candidate.json"
    path.write_text('{"fresh": true}', encoding="utf-8")
    current_mtime = path.stat().st_mtime_ns
    original = dict(engine_ml._SHADOW_CACHE)
    try:
        monkeypatch.setenv("ML_CANDIDATE_MODEL_PATH", str(path))
        engine_ml._SHADOW_CACHE.update({
            "loaded": True,
            "booster": _FakeBooster(),
            "feature_cols": ["old_feature"],
            "version": "old-candidate",
            "metrics": {},
            "error": None,
            "file_mtime_ns": current_mtime - 1,
        })
        with patch.object(
            engine_ml,
            "_restore_durable_candidate_if_enabled",
            return_value=True,
        ) as restore, patch.object(
            engine_ml,
            "load_model_with_metadata",
            return_value=(
                _FakeBooster(),
                ["score_normalized"],
                {"version": "fresh-candidate", "metrics": {"classification_threshold": 0.5}},
                None,
            ),
        ):
            engine_ml._load_shadow_model(sync_durable=True)

        restore.assert_called_once_with(path)
        assert engine_ml._SHADOW_CACHE["booster"] is not None
        assert engine_ml._SHADOW_CACHE["version"] == "fresh-candidate"
        assert engine_ml._SHADOW_CACHE["file_mtime_ns"] == current_mtime
    finally:
        engine_ml._SHADOW_CACHE.clear()
        engine_ml._SHADOW_CACHE.update(original)
