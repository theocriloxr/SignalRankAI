import inspect
import os
from unittest.mock import patch

from ml import artifact_store


def test_artifact_db_timeout_is_bounded_and_configurable():
    with patch.dict(os.environ, {"ML_ARTIFACT_DB_TIMEOUT_SECONDS": "8"}, clear=False):
        assert artifact_store._artifact_query_timeout() == 8.0
    with patch.dict(os.environ, {"ML_ARTIFACT_DB_TIMEOUT_SECONDS": "1"}, clear=False):
        assert artifact_store._artifact_query_timeout() == 5.0


def test_artifact_persistence_uses_bounded_execute_and_commit():
    source = inspect.getsource(artifact_store.persist_active_model_artifact)
    assert "asyncio.wait_for" in source
    assert "session.execute" in source
    assert "session.commit" in source
    assert "_artifact_query_timeout()" in source
