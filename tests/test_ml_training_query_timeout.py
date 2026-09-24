import inspect
import os
from unittest.mock import patch

from ml import train_model


def test_training_query_timeout_is_bounded_and_configurable():
    with patch.dict(os.environ, {"ML_TRAIN_QUERY_TIMEOUT_SECONDS": "7"}, clear=False):
        assert train_model._training_query_timeout() == 7.0
    with patch.dict(os.environ, {"ML_TRAIN_QUERY_TIMEOUT_SECONDS": "1"}, clear=False):
        assert train_model._training_query_timeout() == 5.0


def test_training_evidence_reads_use_async_statement_timeouts():
    source = inspect.getsource(train_model.load_training_data)
    assert "asyncio.wait_for" in source
    assert "session.execute(stmt)" in source
    assert "candle_session.execute(q)" in source
    assert "_training_query_timeout()" in source
