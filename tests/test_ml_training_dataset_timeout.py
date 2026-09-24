import asyncio
import inspect
import os
from unittest.mock import patch

import pytest

from ml import train_model


def test_dataset_timeout_is_bounded_and_configurable():
    with patch.dict(os.environ, {"ML_TRAIN_DATASET_TIMEOUT_SECONDS": "45"}, clear=False):
        assert train_model._training_dataset_timeout() == 45.0
    with patch.dict(os.environ, {"ML_TRAIN_DATASET_TIMEOUT_SECONDS": "5"}, clear=False):
        assert train_model._training_dataset_timeout() == 30.0


def test_main_wraps_dataset_load_with_total_timeout_and_stage_logs():
    source = inspect.getsource(train_model.main)
    assert "dataset_load_start" in source
    assert "dataset_load_complete" in source
    assert "asyncio.wait_for" in source
    assert "_training_dataset_timeout()" in source
    assert "reason=dataset_timeout" in source
