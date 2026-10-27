"""Bounded read-only SDK calls in a separately locked Python environment.

Optional data SDKs have dependency requirements that conflict with the Telegram
runtime. No SDK can replace that runtime's packages or receive trading commands.
Only normalized data and static error codes cross this process boundary.
"""
from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

logger = logging.getLogger(__name__)
_OPERATIONS = {
    "alpaca_bars": ("ALPACA_API_KEY", "ALPACA_API_SECRET", "APCA_API_KEY_ID", "APCA_API_SECRET_KEY"),
    "marketdata_bars": ("MARKETDATA_TOKEN",),
    "ccxt_bars": (),
    "ibkr_bars": (),
    "coinbase_quote": (),
}
_SYSTEM_ENV = {"SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP", "USERPROFILE",
               "APPDATA", "LOCALAPPDATA", "COMSPEC", "LANG", "LC_ALL"}


def read_sdk(operation: str, payload: dict[str, Any], *, timeout: float = 10.0) -> Any:
    if operation not in _OPERATIONS:
        raise ValueError("unsupported_data_sdk_operation")
    seconds = float(timeout)
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("invalid_data_sdk_timeout")
    seconds = min(30.0, seconds)
    interpreter = str(os.getenv("MARKET_DATA_SDK_PYTHON") or sys.executable).strip()
    if not Path(interpreter).is_absolute() or not Path(interpreter).is_file():
        return None
    request = json.dumps({"operation": operation, "payload": payload, "timeout": seconds}, allow_nan=False)
    if len(request.encode("utf-8")) > 65536:
        raise ValueError("data_sdk_request_too_large")
    env = {key: value for key, value in os.environ.items() if key.upper() in _SYSTEM_ENV}
    env.update({key: os.environ[key] for key in _OPERATIONS[operation] if key in os.environ})
    env.update(PYTHONUTF8="1", PYTHONNOUSERSITE="1")
    worker = Path(__file__).resolve().parents[1] / "market_data_sdk" / "worker.py"
    try:
        # Some SDKs read .env in their working directory automatically.
        # Keep application configuration outside that implicit input path.
        with tempfile.TemporaryDirectory(prefix="signalrank-data-sdk-") as directory:
            result = subprocess.run([interpreter, "-I", str(worker.resolve())], input=request, text=True,
                                    capture_output=True, encoding="utf-8", timeout=seconds, env=env, cwd=directory)
        if result.returncode or len(result.stdout.encode("utf-8")) > 2_000_000:
            return None
        response = json.loads(result.stdout)
        if isinstance(response, dict) and response.get("ok") is not True:
            error = response.get("error")
            if isinstance(error, str) and error.isidentifier() and len(error) <= 80:
                logger.debug("data SDK read unavailable operation=%s error_type=%s", operation, error)
        return response.get("data") if isinstance(response, dict) and response.get("ok") is True else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # Exception messages and child stderr may contain request URLs/tokens.
        logger.debug("data SDK read unavailable operation=%s", operation)
        return None
