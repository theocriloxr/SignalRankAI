from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.quiescent_role import validate_quiescent_environment


def _base() -> dict[str, str]:
    return {
        "RAILWAY_ENVIRONMENT_NAME": "staging",
        "SIGNALRANK_ENV_PROFILE": "staging-certification",
        "RUN_MODE": "analytics",
        "SERVICE_ROLE": "analytics",
        "DECOMPOSED_TOPOLOGY_ENABLED": "1",
        "GLOBAL_EXECUTION_KILL_SWITCH": "1",
        "DATABASE_SCHEMA_GATE_ENABLED": "1",
        "RELEASE_SOURCE_GATE_ENABLED": "1",
        "LIVE_FINANCIAL_FEATURES_ENABLED": "0",
        "REAL_EXECUTION_ENABLED": "0",
        "AUTO_EXECUTION_ENABLED": "0",
        "AUTO_TRADE_ENABLED": "0",
        "COPY_TRADE_ENABLED": "0",
        "MT5_ALLOW_LIVE_ACCOUNTS": "0",
        "BYBIT_EXECUTION_ENABLED": "0",
        "HYPERLIQUID_MAINNET_EXECUTION_ENABLED": "0",
        "REAL_PAYOUTS_ENABLED": "0",
        "AUTOMATIC_PAYOUTS_ENABLED": "0",
        "PAYSTACK_TRANSFERS_ENABLED": "0",
        "PAYMENTS_PUBLIC_ENABLED": "0",
    }


def test_quiescent_certification_accepts_safe_staging_dedicated_role() -> None:
    report = validate_quiescent_environment(_base())
    assert report["status"] == "PASS"
    assert report["role"] == "analytics"
    assert report["engine_owned"] is False
    assert report["telegram_owned"] is False


@pytest.mark.parametrize(
    "name",
    [
        "LIVE_FINANCIAL_FEATURES_ENABLED",
        "REAL_EXECUTION_ENABLED",
        "AUTO_EXECUTION_ENABLED",
        "AUTO_TRADE_ENABLED",
        "COPY_TRADE_ENABLED",
        "MT5_ALLOW_LIVE_ACCOUNTS",
        "BYBIT_EXECUTION_ENABLED",
        "HYPERLIQUID_MAINNET_EXECUTION_ENABLED",
        "REAL_PAYOUTS_ENABLED",
        "AUTOMATIC_PAYOUTS_ENABLED",
        "PAYSTACK_TRANSFERS_ENABLED",
        "PAYMENTS_PUBLIC_ENABLED",
    ],
)
def test_quiescent_certification_rejects_any_live_money_switch(name: str) -> None:
    env = _base()
    env[name] = "1"
    with pytest.raises(RuntimeError, match="requires financial/execution flags off"):
        validate_quiescent_environment(env)


def test_quiescent_certification_is_staging_only() -> None:
    env = _base()
    env["RAILWAY_ENVIRONMENT_NAME"] = "production"
    with pytest.raises(RuntimeError, match="requires staging environment"):
        validate_quiescent_environment(env)


def test_quiescent_certification_requires_kill_switch() -> None:
    env = _base()
    env["GLOBAL_EXECUTION_KILL_SWITCH"] = "0"
    with pytest.raises(RuntimeError, match="GLOBAL_EXECUTION_KILL_SWITCH"):
        validate_quiescent_environment(env)


def test_quiescent_certification_rejects_monolith() -> None:
    env = _base()
    env["DECOMPOSED_TOPOLOGY_ENABLED"] = "0"
    env["RUN_MODE"] = "all"
    env["SERVICE_ROLE"] = "all"
    with pytest.raises(RuntimeError, match="forbids role=all/dev"):
        validate_quiescent_environment(env)


def test_quiescent_direct_script_invocation_resolves_repo_imports() -> None:
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update(
        {
            "RAILWAY_ENVIRONMENT_NAME": "production",
            "SIGNALRANK_ENV_PROFILE": "staging-certification",
            "RUN_MODE": "analytics",
            "GLOBAL_EXECUTION_KILL_SWITCH": "1",
            "DATABASE_SCHEMA_GATE_ENABLED": "1",
            "RELEASE_SOURCE_GATE_ENABLED": "1",
        }
    )
    result = subprocess.run(
        [sys.executable, "scripts/quiescent_role.py"],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "ModuleNotFoundError" not in combined
    assert "quiescent certification requires staging environment" in combined


def test_start_sh_invokes_quiescent_runner_as_module() -> None:
    root = Path(__file__).resolve().parents[1]
    start = (root / "start.sh").read_text(encoding="utf-8")
    assert "exec python -u -m scripts.quiescent_role" in start
