"""Untrusted provider timestamps cannot hang validation or certify future data."""
import argparse
import asyncio
import os
import subprocess
import sys

import pytest

from data.provider_catalog import get_provider_spec
from scripts import certify_providers as provider


def test_positive_infinity_cannot_hang_any_timestamp_normalizer():
    code = '''
import sys
sys.modules.setdefault("eventlet", None)
from data.market_data import _validate_ohlcv
from data.provider_catalog import get_provider_spec
from scripts.certify_market_classes import _latest_age
from scripts.certify_providers import _freshness_validation
row = {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1, "timestamp": float("inf")}
assert _validate_ohlcv([row]) is False
assert _latest_age({"last_timestamp": float("inf")}) is None
assert _freshness_validation(get_provider_spec("coinbase"), {"last_timestamp": float("inf")})[0] is False
'''
    # A subprocess deadline also makes the original infinite-loop regression
    # fail promptly instead of hanging the complete suite.
    process = subprocess.run([sys.executable, "-c", code], env=os.environ.copy(), capture_output=True, text=True, timeout=15)
    assert process.returncode == 0, process.stderr


@pytest.mark.parametrize("stamp", [float("nan"), float("-inf"), 0, -1, "invalid"])
def test_nonfinite_or_invalid_provider_timestamp_is_not_execution_eligible(stamp):
    result = provider._freshness_validation(get_provider_spec("coinbase"), {"last_timestamp": stamp})
    assert result[0] is False and result[3] == "invalid_last_timestamp"


def test_future_timestamp_is_not_clamped_into_a_fresh_certification(monkeypatch):
    monkeypatch.setattr(provider.time, "time", lambda: 1_800_000_000.0)
    future = provider._freshness_validation(get_provider_spec("coinbase"), {"last_timestamp": 1_800_001_000.0})
    assert future[0] is False and future[3] == "future_last_timestamp"
    fresh = provider._freshness_validation(get_provider_spec("coinbase"), {"last_timestamp": 1_799_999_990_000.0})
    assert fresh[0] is True and fresh[1] == 10.0


@pytest.mark.parametrize("name,timeout,limit", [("unknown-provider", 1, 10), ("coinbase", float("nan"), 10), ("coinbase", 0, 10), ("coinbase", 1, 0), ("coinbase", 1, 1)])
def test_bad_provider_cli_scope_cannot_report_a_successful_empty_run(tmp_path, name, timeout, limit):
    args = argparse.Namespace(providers=name, timeout=timeout, limit=limit, live=True,
                              output_dir=str(tmp_path / "certificate"), require_asset_classes="")
    with pytest.raises(RuntimeError):
        asyncio.run(provider._run(args))
    assert not (tmp_path / "certificate").exists()
