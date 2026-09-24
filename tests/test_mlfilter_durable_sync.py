import os
from unittest.mock import patch

from ml import inference


def test_mlfilter_durable_sync_is_bounded_and_calls_primary_restore():
    original = dict(inference._DURABLE_SYNC_STATE)
    try:
        inference._DURABLE_SYNC_STATE["last_attempt"] = 0.0
        with patch.dict(
            os.environ,
            {
                "ML_DURABLE_ARTIFACT_SYNC_ENABLED": "1",
                "ML_DURABLE_ARTIFACT_SYNC_INTERVAL_SECONDS": "60",
            },
            clear=False,
        ), patch.object(
            inference.time, "monotonic", side_effect=[100.0, 120.0]
        ), patch(
            "ml.artifact_store.restore_active_model_artifact_from_database_sync",
            return_value=True,
        ) as restore:
            assert inference._sync_durable_model_if_due("/tmp/model.json") is True
            assert inference._sync_durable_model_if_due("/tmp/model.json") is False

        restore.assert_called_once()
        args, kwargs = restore.call_args
        assert args[0] == "/tmp/model.json"
        assert kwargs["model_name"] == "primary"
    finally:
        inference._DURABLE_SYNC_STATE.clear()
        inference._DURABLE_SYNC_STATE.update(original)
